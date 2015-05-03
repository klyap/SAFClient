# coding=utf8

"""Reference client also used in integration tests."""

import collections
import datetime
import hashlib
import importlib
import logging
import platform
import threading
import urllib
import urllib2

import google.protobuf
import poster
import yaml

import util

from messages import common_pb2, event_pb2, heartbeat_pb2, client_messages_pb2


SOFTWARE_VERSION = 'SAFCSNclient v1.0b'

# Unless specifically instructed to use a remote server, use the local server.
DEFAULT_SERVER = 'localhost:8080'
DEFAULT_NAMESPACE = 'test'

# the maximum number of pending data files that will be sent on each heartbeat
MAX_PENDING_UPLOADS = 10

# SAF endpoints.
API_URL_TEMPLATE = 'http://{server}/api/{version}/{namespace}/{action}'
JSON_URL_TEMPLATE = API_URL_TEMPLATE.replace('/api/', '/json/')
API_VERSION = 'v1'
EVENT_ENDPOINT = 'event/{client_id}'
CLIENT_CREATE_ENDPOINT = 'client/create'
CLIENT_UPDATE_ENDPOINT = 'client/update/{client_id}'
CLIENT_METADATA_ENDPOINT = 'client/metadata/{client_id}'
CLIENT_KEYVALUE_ENDPOINT = 'client/get-keyvalue/{client_id}'
CLIENT_EDIT_TOKEN_ENDPOINT = 'client/edit-token/{client_id}'
HEARTBEAT_ENDPOINT = 'heartbeat/{client_id}'

# Properties of object Client.
CLIENT_FIELDS = [
    ('server', None),
    ('namespace', None),
    ('client_id', None),
    ('client_secret', None),
    ('message_id', 0),
    ('latest_request_id', 0),
    ('location_changed', False),
]

# Properties of Client's client_data object.
CLIENT_DATA_FIELDS = [
    'building',
    'floor',
    'latitude',
    'longitude',
    'location_source_type',
    'location_description',
    'mobility_type',
    'name',
    'operating_system',
    'software_version',
]

# Static init necesarry for multipart post used in submitting waveform data.
# http://atlee.ca/software/poster/
poster.streaminghttp.register_openers()


class Client(object):
    """
    Reference Client.

    Notes
    -----
    For ease of implementation, Client's access several functions of Sensor
    objects directly. To avoid this, for fully asynchronous communication or
    a more complex data structure, the Client should communicate with Sensor
    children through a queue or other channel-like mechanism.

    """

    def __init__(self, config=None, send_event_fn=None):
        if config is None:
            config = {}
        # Event sending will be synchronous if send_event_fn is not overridden.
        if send_event_fn is None:
            send_event_fn = self.send_sensor_event
        # Set all client properties from config or default.
        for field, default in CLIENT_FIELDS:
            setattr(self, field, config.get(field, default))
        # Create locks for changing metadata and incrementing the message_id.
        self.metadata_lock = threading.RLock()
        self.message_id_lock = threading.Lock()
        # Fields changed since last update.
        self.delta_fields = set(config.get('delta_fields', []))
        # Key/Value objects that have not been provided to the server.
        self.unsent_keyvalue = set(config.get('unsent_keyvalue', []))
        self.client_data = client_messages_pb2.ClientMetadata()
        # Set all client_data fields from config.
        for field in CLIENT_DATA_FIELDS:
            if field in config:
                setattr(self.client_data, field, config[field])
        # Compare OS/software version on startup to see if client was moved
        # to a new architecture or if the underlying OS/software has been
        # updated.
        client_os = platform.platform(aliased=True)
        if self.client_secret:
            if self.client_data.operating_system != client_os:
                self.delta_fields.add('operating_system')
            if self.client_data.software_version != SOFTWARE_VERSION:
                self.delta_fields.add('software_version')
        self.client_data.operating_system = client_os
        self.client_data.software_version = SOFTWARE_VERSION
        # Extra keyvalue metadata for this client.
        self.keyvalue = {}
        for kv_dict in config.get('keyvalue', {}):
            self.add_key_value(kv_dict['key'], kv_dict['value'],
                               kv_dict.get('field', 'string_value'))
        self.sensors = {}
        # Sensors awaiting id assignments.
        self.unassigned_sensors = []
        # List of no longer available sensors.
        self.removed_sensors = []
        for sensor_dict in config.get('sensors', []):
            sensor_module = importlib.import_module(sensor_dict['module'])
            sensor_class = getattr(sensor_module, sensor_dict['class'])
            sensor = sensor_class(send_event_fn=send_event_fn,
                                  config=sensor_dict)
            
            sensor_id = sensor_dict.get('sensor_id')
            if sensor_id is not None:
                self.sensors[sensor_id] = sensor, SensorStats()
                sensor.set_sensor_id(sensor_id)
            else:
                self.unassigned_sensors.append(sensor)

    def to_dict(self):
        """Generates a dictionary that can be passed to __init__ on startup."""
        with self.metadata_lock:
            details = {}
            for field, _ in CLIENT_FIELDS:
                details[field] = getattr(self, field)
            for field in CLIENT_DATA_FIELDS:
                if self.client_data.HasField(field):
                    details[field] = getattr(self.client_data, field)
            if self.delta_fields:
                details['delta_fields'] = []
                for field in self.delta_fields:
                    details['delta_fields'].append(field)
            if self.unsent_keyvalue:
                details['unsent_keyvalue'] = []
                for key in self.unsent_keyvalue:
                    details['unsent_keyvalue'].append(key)
            if self.sensors or self.unassigned_sensors:
                details['sensors'] = []
                for sensor_id, (sensor, _) in self.sensors.viewitems():
                    sensor_details = sensor.to_dict()
                    sensor_details['sensor_id'] = sensor_id
                    details['sensors'].append(sensor_details)
                for sensor in self.unassigned_sensors:
                    details['sensors'].append(sensor.to_dict())
            if self.keyvalue:
                details['keyvalue'] = []
                for key, (msg, field) in self.keyvalue.viewitems():
                    details['keyvalue'].append({
                        'key': key,
                        'field': field,
                        'value': getattr(msg, field),
                    })
            return details

    @classmethod
    def from_file(cls, filename):
        """Shorthand for reading a stored config file and creating a Client."""
        config = read_config(filename)
        return cls(config=config)

    def to_file(self, filename):
        """Shorthand for generating a dictionary and writing it to a file."""
        with self.metadata_lock:
            config = self.to_dict()
            save_config(config, filename)

    def send_sensor_event(self, sensor_id, event_time, values):
        """Send an event from a given sensor."""
        event_message = event_pb2.EventMessage()
        self._sign_message(event_message.client_signature)
        self._set_location_if_changed(event_message)
        event_message.event.sensor_id = sensor_id
        event_message.event.date = util.date_format(event_time)
        # Always send location for faster processing.
        event_message.latitude = self.client_data.latitude
        event_message.longitude = self.client_data.longitude
        for value in values:
            event_message.event.readings.append(value)
        _, stats = self.sensors[sensor_id]
        time_window, event_count = stats.add_event(event_time)
        event_message.event.time_window = time_window
        event_message.event.event_count = event_count
        logging.info('Sending event from sensor %d -> %s', sensor_id, values)
        return self._send_and_get_response(
            event_message,
            EVENT_ENDPOINT,
            event_pb2.EventResponse
        )

    def send_event(self, event_time, values):
        """Alias to call send_sensor_event on the only attached sensor."""
        if not self.sensors or len(self.sensors) > 1:
            raise ValueError('send_event can only be called if only one '
                             'sensor is attached.')
        return self.send_sensor_event(
            self.sensors.keys()[0], event_time, values)

    def send_heartbeat(self, status_change=None):
        heartbeat_message = heartbeat_pb2.HeartbeatMessage()
        current_time = util.system_time()
        self._sign_message(heartbeat_message.client_signature,
                           date=current_time)
        self._set_location_if_changed(heartbeat_message)
        heartbeat_message.latest_request_id = self.latest_request_id
        offer_order = []
        if status_change:
            heartbeat_message.status_change = status_change
        else:
            for sensor_id, (sensor, stats) in self.sensors.viewitems():
                event_rate = heartbeat_message.event_rates.add()
                event_rate.sensor_id = sensor_id
                event_rate.event_count, event_rate.time_window = (
                    stats.get_window_details(current_time))
                #offer_pb, data, filename = sensor.get_current_data()
                #if offer_pb and data:
                #    offer_order.append((sensor_id, data, filename))
                #    data = heartbeat_message.current_data_offers.add()
                #    data.CopyFrom(offer_pb)
                # Now check if the sensor has any older data files waiting to be uploaded
                # and limit the number of these to avoid overtaxing the system
                pending_uploads = sensor.datafiles_not_yet_uploaded()
                if len(pending_uploads) > 0:
                    logging.info('There are %s pending data files to upload', len(pending_uploads))
                    pending_count = 0 
                    for filename in pending_uploads:
                        offer_pb, data = sensor.get_filename_data(filename)
                        if offer_pb and data:
                            logging.info('Adding data from file %s to offer', filename)
                            offer_order.append((sensor_id, data, filename))
                            data = heartbeat_message.current_data_offers.add()
                            data.CopyFrom(offer_pb)
                            pending_count += 1
                            if pending_count >= MAX_PENDING_UPLOADS:
                                logging.warn('Limit of %s pending uploads added', pending_count)
                                break
                    

        heartbeat_response = self._send_and_get_response(
            heartbeat_message,
            HEARTBEAT_ENDPOINT,
            heartbeat_pb2.HeartbeatResponse
        )


        if heartbeat_response.status.type == common_pb2.SUCCESS:
            with self.metadata_lock:
                self.latest_request_id = heartbeat_response.latest_request_id
                self.location_changed = False
            for url, (sensor_id, data, filename) in zip(
                    heartbeat_response.current_data_upload_urls, offer_order):
                if not url:
                    logging.info('Data for sensor %s was not requested by '
                                 'the server.', sensor_id)
                    continue
                upload_sensor_reading(url, value=data)
                logging.info('Sensor %s File %s was uploaded', sensor_id, filename)
                sensor, _ = self.sensors[sensor_id]
                sensor.mark_file_uploaded(filename)
            if heartbeat_response.metadata_changed:
                self.get_metadata()
            # TODO: Handle data requests.
        else:
            logging.error("Heartbeat response was %s", heartbeat_response)

    def register(self, server=None, namespace=None):
        # If previously registered, clear fields.
        with self.metadata_lock:
            if self.client_secret:
                self.client_id = None
                self.client_secret = None
                self.message_id = 0
                self.latest_request_id = 0
            if server:
                self.server = server
            elif self.server is None:
                self.server = DEFAULT_SERVER
            if namespace:
                self.namespace = namespace
            elif self.namespace is None:
                self.namespace = DEFAULT_NAMESPACE
            registration_message = client_messages_pb2.ClientCreateMessage()
            registration_message.client_data.CopyFrom(self.client_data)
            self._unassign_all_sensors()
            self._add_unassigned(registration_message.attached_sensors)
            registration_response = self._send_and_get_response(
                registration_message,
                CLIENT_CREATE_ENDPOINT,
                client_messages_pb2.ClientCreateResponse
            )
            if registration_response.status.type == common_pb2.SUCCESS:
                self.client_id = registration_response.client_id
                self.client_secret = registration_response.client_secret
                self.latest_request_id = (
                    registration_response.latest_request_id)
                self.location_changed = False
                self.delta_fields.clear()
                self.unsent_keyvalue.clear()
                self.removed_sensors = []
                self._assign_ids(registration_response.sensor_ids)

    def send_update(self):
        """Update the metadata of the client at the server."""
        update_message = client_messages_pb2.ClientUpdateMessage()
        self._sign_message(update_message.client_signature)
        self._set_location_if_changed(update_message.client_data)
        self._add_unassigned(update_message.new_sensors)
        _copy_deltas(self.delta_fields, self.client_data,
                     update_message.client_data)
        for key in self.unsent_keyvalue:
            metadata_msg = update_message.client_data.other_metadata.add()
            metadata_msg.CopyFrom(self.keyvalue[key][0])
        for sensor_id in self.removed_sensors:
            update_message.removed_sensors.append(sensor_id)
         
        # We update all the sensors    
        for sensor_id, (sensor, stats) in self.sensors.viewitems():
            sensor_data = sensor.get_metadata()
            if sensor_data:
                 revised_sensor_data = update_message.updated_sensors.add()
                 revised_sensor_data.CopyFrom(sensor_data)
    
            
        registration_response = self._send_and_get_response(
            update_message,
            CLIENT_UPDATE_ENDPOINT,
            client_messages_pb2.ClientUpdateResponse
        )
        if registration_response.status.type == common_pb2.SUCCESS:
            with self.metadata_lock:
                self.location_changed = False
                self.delta_fields.clear()
                self.unsent_keyvalue.clear()
                self.removed_sensors = []
                self._assign_ids(registration_response.sensor_ids)

    def get_metadata(self):
        """Update the metadata of the client from the server."""
        metadata_message = client_messages_pb2.ClientMetadataRequest()
        self._sign_message(metadata_message.client_signature)
        metadata_response = self._send_and_get_response(
            metadata_message,
            CLIENT_METADATA_ENDPOINT,
            client_messages_pb2.ClientMetadataResponse
        )
        if metadata_response.status.type == common_pb2.SUCCESS:
            with self.metadata_lock:
                self.client_data.CopyFrom(metadata_response.client_data)

    def get_edit_token(self):
        """Create a new editor token and return the editor url and token."""
        token_message = client_messages_pb2.ClientEditorTokenRequest()
        self._sign_message(token_message.client_signature)
        token_response = self._send_and_get_response(
            token_message,
            CLIENT_EDIT_TOKEN_ENDPOINT,
            client_messages_pb2.ClientEditorTokenResponse
        )
        if token_response.status.type == common_pb2.SUCCESS:
            return token_response.editor_url, token_response.token
        return None, None

    def change_location(self, (latitude, longitude)):
        """Change client location and indicate that it should be sent."""
        self.client_data.latitude = latitude
        self.client_data.longitude = longitude
        self.location_changed = True

    def add_key_value(self, key, value, field='string_value'):
        """Add a key/value metadata pair to the client."""
        if key in self.keyvalue:
            kv_msg, _ = self.keyvalue[key]
        else:
            kv_msg = self.client_data.other_metadata.add()
            self.keyvalue[key] = kv_msg, field
            kv_msg.key = key
        self.unsent_keyvalue.add(key)
        setattr(kv_msg, field, value)

    def add_sensor(self, sensor):
        """Add a new sensor. Call send_update to inform the server."""
        self.unassigned_sensors.append(sensor)

    def _add_unassigned(self, message):
        """Add unassigned sensors to a new or updated registration message."""
        for sensor in self.unassigned_sensors:
            sensor_data = message.add()
            sensor_data.CopyFrom(sensor.get_metadata())

    def _assign_ids(self, id_list):
        """
        ID assignment cannot be performed unless the lists are equal length.

        Raises an exception if lists are unequal in length.

        """
        if not id_list:
            return
        try:
            if len(id_list) != len(self.unassigned_sensors):
                if len(id_list) > len(self.unassigned_sensors):
                    raise ValueError('Too many IDs provided for sensors.')
                else:
                    raise ValueError('Not enough IDs provided for sensors.')
            for sensor_id, sensor in zip(id_list, self.unassigned_sensors):
                self.sensors[sensor_id] = sensor, SensorStats()
                sensor.set_sensor_id(sensor_id)
            self.unassigned_sensors = []
        except ValueError:
            # FIXME: There is a potential race condition in a threaded client
            # where a sensor could be added while an outstanding update or
            # registration is ongoing. That would trigger this case and force
            # all of the unassigned sensors to register as new.
            self.removed_sensors.extend(id_list)
            # TODO: Automatically attempt update with attached_sensors?
            logging.exception('Incorrect number of sensor ids.')

    def _unassign_all_sensors(self):
        """
        Unassign all sensors for re-registration.

        If we explicitly ask for a registration even if we have already
        registered, identify all sensors as unassigned.

        """
        if self.sensors:
            for sensor, _ in self.sensors.viewvalues():
                self.unassigned_sensors.append(sensor)
            self.sensors.clear()

    def _set_location_if_changed(self, message):
        """Shorthand to include location data only if it has changed."""
        if self.location_changed:
            message.latitude = self.client_data.latitude
            message.longitude = self.client_data.longitude

    def _sign_message(self, client_signature, date=None):
        """Fill out ClientSignature portion of a larger message."""
        date = date if date else util.system_time()
        client_signature.date = util.date_format(date)
        with self.message_id_lock:
            client_signature.message_id = self.message_id
            self.message_id += 1
        # Create a hash of the message date and the client's secret to use as a
        # simple signature to verify the message origin.
        signature = hashlib.sha256(
            '{}/{}/{}'.format(client_signature.date,
                              client_signature.message_id,
                              self.client_secret))
        client_signature.signature = signature.hexdigest()

    def _send_and_get_response(self, message, action, response_class):
        """
        Send a protobuf message to the specified endpoint and parse a response.
        """
        url = API_URL_TEMPLATE.format(
            server=self.server,
            version=API_VERSION,
            namespace=self.namespace,
            action=action.format(client_id=self.client_id),
            #client_id=self.client_id
        )
        headers = {
            'User-Agent': SOFTWARE_VERSION,
            'Content-Type': 'application/x-protobuf',
            'Content-Length': message.ByteSize(),
        }
        data = message.SerializeToString()
        request = urllib2.Request(url, data, headers)
        logging.debug('Sending: %s', message)
        logging.debug('Sending to: %s', request.get_full_url())
        raw_response = _read_request(request)
        response = response_class()
        try:
            response.ParseFromString(raw_response)
        except google.protobuf.message.DecodeError:
            logging.warning('Response from server malformed. Received: %s',
                            raw_response)
            # Can reraise.
        else:
            logging.debug('Received: %s', response)
        # Empty if there was a decode error.
        return response


class SensorStats(object):

    """Used to keep track of the event rate of individual sensors."""

    # Time window for which event statistics are captured for.
    TIME_WINDOW_MAX = datetime.timedelta(minutes=10)

    def __init__(self):
        # Time at which this sensor was attached. Determines window size when
        # the sensor has not been attached for at least Client.MAX_WINDOW_SIZE
        # time.
        self.startup_time = util.system_time()
        # Check window size if the sensor has not been attached for at least
        # as long as Client.MAX_WINDOW_SIZE.
        self.check_window_size = True
        # List of events that have occurred in the last time window time.
        self.event_list = collections.deque()
        self._modification_lock = threading.Lock()

    def get_window_details(self, time, is_event=False):
        if self.check_window_size:
            elapsed_time = time - self.startup_time
            if elapsed_time > self.TIME_WINDOW_MAX:
                # Client has been running for TIME_WINDOW_MAX duration.
                with self._modification_lock:
                    self.check_window_size = False
                window_size = self.TIME_WINDOW_MAX
            window_size = elapsed_time
        else:
            window_size = self.TIME_WINDOW_MAX
        with self._modification_lock:
            while self.event_list and (
                    time - self.event_list[0] > self.TIME_WINDOW_MAX):
                self.event_list.popleft()
            if is_event:
                self.event_list.append(time)
        time_window = int(round(window_size.total_seconds()))
        event_count = len(self.event_list)
        return time_window, event_count

    def add_event(self, time):
        return self.get_window_details(time, is_event=True)


def read_config(filename):
    """Convenience function for reading YAML config files."""
    with open(filename) as config_file:
        config = yaml.load(config_file.read())
    return config


def save_config(config, filename):
    """Convenience function for writing YAML config files."""
    with open(filename, 'w') as config_file:
        config_file.write(yaml.dump(config, default_flow_style=False))


def download_sensor_reading(reading_id, server, namespace, token=None):
    """Download the reading specified from the indicated server/namespace."""
    url = JSON_URL_TEMPLATE.format(
        server=server,
        version=API_VERSION,
        namespace=namespace,
        action='data/reading/{}'.format(reading_id),
    )
    if token:
        url = '{}?{}'.format(url, urllib.urlencode({'token': token}))
    headers = {'User-Agent': SOFTWARE_VERSION}
    request = urllib2.Request(url=url, headers=headers)
    logging.debug('Sending to: %s', request.get_full_url())
    response = urllib2.urlopen(request)
    disposition = response.headers['Content-Disposition']
    filename = '"'.join(disposition.split('"')[1:-1])
    logging.debug('Got file: %s.', filename)
    return filename, response.read()


def upload_sensor_reading(url, value=None, fileobj=None, filename='data',
                          filetype='application/octet-stream'):
    """
    Upload the binary data to the URL specified as a multipart post.

    Function keyword arguments are mirrors of `poster.encode.MultipartParam`
    keyword objects. One of either `value` or `fileobj` must be specified.

    """
    param = poster.encode.MultipartParam(
        'payload',
        value=value, fileobj=fileobj, filename=filename, filetype=filetype)
    data, headers = poster.encode.multipart_encode([param])
    headers['User-Agent'] = SOFTWARE_VERSION
    request = urllib2.Request(url, data, headers)
    logging.debug('Sending to: %s', request.get_full_url())
    raw_response = _read_request(request)
    response_pb = heartbeat_pb2.SensorReadingUploadResponse()
    response_pb.ParseFromString(raw_response)
    logging.debug('Received: %s', response_pb)
    if response_pb.status.type == common_pb2.SUCCESS:
        return response_pb.sensor_reading_id
    else:
        return None


def _read_request(request):
    """Wrapper around reading a response to always get the response body."""
    try:
        raw_response = urllib2.urlopen(request).read()
    except urllib2.HTTPError, err:
        raw_response = err.read()
    return raw_response


def _copy_deltas(delta_fields, source, dest):
    """Helper function to copy changed fields."""
    for field in delta_fields:
        setattr(dest, field, getattr(source, field))

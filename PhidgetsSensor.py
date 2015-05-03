# coding=utf-8

"""Phidgets CSN Sensor"""
import sys
import os
import errno
import shutil
import math
import numpy
import datetime
import hashlib
import logging
import threading
import Queue
from multiprocessing import Process

import cPickle as pickle


import util

from messages import common_pb2, heartbeat_pb2, client_messages_pb2

from Phidgets import Phidget
from Phidgets.PhidgetException import PhidgetErrorCodes, PhidgetException
from Phidgets.Events.Events import AccelerationChangeEventArgs, AttachEventArgs, DetachEventArgs, ErrorEventArgs
from Phidgets.Devices.Spatial import Spatial, SpatialEventData, TimeSpan
from Tkconstants import HORIZONTAL


RANDOM_WAIT_TIME = 10
MINIMUM_WAIT_TIME = 2

# our special order CSN Phidgets are scaled to +/- 2g instead of +/- 6g
PHIDGETS_ACCELERATION_TO_G = 1.0/3.0
# we request samples at 250 per second
PHIDGETS_NOMINAL_DATA_INTERVAL_MS = 4
# We decimate to 50 samples per second
PHIDGETS_DECIMATION = 5

LTA = 10.0
STA = 0.5
Gap = 1.0
KSIGMA_THRESHOLD = 3.0

RECENT_PICKS_COUNT = 100

MINIMUM_REPICK_INTERVAL_SECONDS = datetime.timedelta(seconds=1)
PHIDGETS_RESAMPLED_DATA_INTERVAL_MS = PHIDGETS_NOMINAL_DATA_INTERVAL_MS * PHIDGETS_DECIMATION
FILESTORE_NAMING = "%Y%m%dT%H%M%S"
PRECISION_NAMING = "%Y%m%dT%H%M%S.%f"



class Sensor(object):
    """
    Phidgets sensor class obeying the expected Sensor contract.

    Expected functions for a Sensor are:

    run
        A function which takes a threading.Event object which is set when the
        sensor should halt. The body of run should be used for processing
        sensor data, and is run in its own thread by the controller.

    get_current_data
        Used to respond to requests for ongoing sensor data. Must be thread
        safe. The result is a tuple of metadata and a block of data to be
        uploaded, if desired. To opt not to return data, the sensor can
        simply return `(None, None)`. The function can block to request data
        from the sensor thread, if necessary.

    set_sensor_id
        Set the sensor_id for this sensor. Must be thread safe. Without a
        sensor id, events cannot be sent.

    to_dict
        Return a dictionary containing all fields that need persisted and the
        special fields 'module' and 'class', which tell the client how to
        instantiate the sensor. The dictionary will be passed as the second
        argmuent to __init__ when deserializing a client. Must be thread safe.

    """
    
    

    def __init__(self, send_event_fn=None, config=None):
        if not config:
            config = {}
        if send_event_fn:
            self._send_event = send_event_fn
        self.phidget_attached = False
        self.sensor_data_lock = threading.Lock()
        # Set of fields that have changed since the last update.
        self.delta_fields = set()
        self.sensor_data = client_messages_pb2.SensorMetadata()
        self.sensor_data.sensor_type = common_pb2.ACCELEROMETER_3_AXIS
        self.sensor_data.calibrated = True
        self.sensor_data.model = 'Phidgets 1056'
        if 'serial' in config:
            self.sensor_data.serial = config.get('serial')
        else:
            self.sensor_data.serial = ''
        if 'datastore' in config:
            self.datastore = config.get('datastore')
        else:
            self.datastore = '/tmp/phidgetsdata' 
        if 'time_server' in config:
            self.time_server = config.get('time_server')
        else:
            self.time_server = None           
        self.datastore_uploaded = self.datastore + '/uploaded'
        self.datastore_corrupted = self.datastore + '/corrupted'
        logging.info('Sensor datastore directory is %s',self.datastore)
        self.sensor_data.units = 'g'
        self.sensor_data.num_samples = 50
        self.sensor_data.sample_window_size = 1
        self.accelerometer = None
        self.time_start = None
        self.reported_clock_drift = datetime.timedelta(seconds=0)
        self.file_store_interval = datetime.timedelta(seconds=600)
        self.last_phidgets_timestamp = None
        self.last_datastore_filename = None
        self.last_datastore_filename_uploaded = None
        # a lock for updating the timing variables
        self.timing_lock = threading.Lock()
        
        self.timing_gradient = 0.0
        self.timing_intercept = 0.0
        self.timing_base_time = datetime.datetime.utcnow()
        
        self.recent_picks = []
        
        # Make sure data directory exists
        try:
            os.makedirs(self.datastore)
        except OSError as exception:
            logging.info('Notification for directories %s', exception)
        try:
            os.makedirs(self.datastore_uploaded)
        except OSError as exception:
            logging.info('Notification for directories %s', exception)
        try:            
            os.makedirs(self.datastore_corrupted)
        except OSError as exception:
            logging.info('Notification for directories %s', exception)
  
                  
        # start the Picker thread
        self.sensor_readings_queue = Queue.Queue()
        
        thread = threading.Thread(target=self.Picker, args=['algorithm'])
        thread.setDaemon(True)
        thread.start()
        
        self.sensor_readings_queue.join()
        
        logging.info('Client initialised: now starting Phidget')
        
        self.data_buffer = []
         
        # Start the Phidget       
        self.StartPhidget()
                 
        self.sensor_data.serial = str(self.accelerometer.getSerialNum())
       
        self.DisplayDeviceInfo()
        


    def StartPhidget(self):
        # Initialise the Phidgets sensor
      
        self.phidget_attached = False
        self.time_start = None
        
        try:
            if self.accelerometer:
                self.accelerometer.closePhidget()
            
            self.accelerometer = Spatial()
            self.accelerometer.setOnAttachHandler(self.AccelerometerAttached)
            self.accelerometer.setOnDetachHandler(self.AccelerometerDetached)
            self.accelerometer.setOnErrorhandler(self.AccelerometerError)
            self.accelerometer.setOnSpatialDataHandler(self.SpatialData)
            
            self.accelerometer.openPhidget()
            
            self.accelerometer.waitForAttach(10000)
            
            # set data rate in milliseconds (we will decimate from 4ms to 20ms later)
            self.accelerometer.setDataRate(PHIDGETS_NOMINAL_DATA_INTERVAL_MS)

        except RuntimeError as e:
            logging.error("Runtime Exception: %s", e.details)
            return
        except PhidgetException as e:
            logging.error("Phidget Exception: %s. Is the Phidget not connected?", e.details)
            return

        
        self.phidget_attached = True
        


            
    def Picker(self, args):
        logging.info('Initialise picker with args %s', args)
        # LTA = 10 seconds
        # Gap = 1 seconds
        # STA = 0.5 seconds
        delta = PHIDGETS_NOMINAL_DATA_INTERVAL_MS * PHIDGETS_DECIMATION * 0.001
        LTA_count = int(LTA / delta)
        STA_count = int(STA / delta)
        Gap_count = int(Gap / delta)
        ksigma_count = LTA_count + Gap_count + STA_count
        horizontal_accelerations = []
        vertical_accelerations = []
        last_horizontal_pick_timestamp = last_vertical_pick_timestamp = self.GetNtpCorrectedTimestamp()
        
        
        in_pick_horizontal = False
        in_pick_vertical = False

        count_readings = 0
        timestamp_reading = datetime.datetime.utcnow()
        
        while True:
            (timestamp, accelerations) = self.sensor_readings_queue.get()
            
            count_readings += 1
            """
            if count_readings == 5*PHIDGETS_DECIMATION:
                timestamp_now = datetime.datetime.utcnow()
                logging.info("Picker: %s readings in %s seconds", count_readings, (timestamp_now-timestamp_reading).total_seconds())
                timestamp_reading = timestamp_now
                count_readings = 0
            """
            
            
            horizontal = math.sqrt(accelerations[0]*accelerations[0] + accelerations[1]*accelerations[1])
            north = accelerations[0]
            east = accelerations[1]
            vertical = accelerations[2]
            horizontal_accelerations.append(horizontal)
            vertical_accelerations.append(vertical)
            number_in_list = len(horizontal_accelerations)
            if number_in_list < ksigma_count:
                continue

            lta_horizontal_std = numpy.std(horizontal_accelerations[:LTA_count])
            lta_vertical_std = numpy.std(vertical_accelerations[:LTA_count])
            lta_horizontal_lta = numpy.mean(horizontal_accelerations[:LTA_count])
            lta_vertical_lta = numpy.mean(vertical_accelerations[:LTA_count])
            #sta_horizontal_std = numpy.std(horizontal_accelerations[LTA_count+Gap_count:])
            #sta_vertical_std = numpy.std(vertical_accelerations[LTA_count+Gap_count:])
                
            sta_horizontal_mean = sum([abs(a-lta_horizontal_lta) for a in horizontal_accelerations[LTA_count+Gap_count:]]) / STA_count
            ksigma_horizontal = sta_horizontal_mean / lta_horizontal_std
                
            sta_vertical_mean = sum([abs(a-lta_vertical_lta) for a in vertical_accelerations[LTA_count+Gap_count:]]) / STA_count
            ksigma_vertical = sta_vertical_mean / lta_vertical_std
               
            if not in_pick_horizontal and timestamp-last_horizontal_pick_timestamp > MINIMUM_REPICK_INTERVAL_SECONDS: 
                if ksigma_horizontal > KSIGMA_THRESHOLD:
                    in_pick_horizontal = True
                    maximum_acceleration_north = abs(north)
                    maximum_acceleration_east = abs(east)
                    last_horizontal_pick_timestamp = timestamp
                    ksigma_horizontal_at_pick = ksigma_horizontal
                    logging.info('Horizontal pick at %s ksigma=%s',timestamp,ksigma_horizontal_at_pick)
            if not in_pick_vertical and timestamp-last_vertical_pick_timestamp > MINIMUM_REPICK_INTERVAL_SECONDS: 
                if ksigma_vertical > KSIGMA_THRESHOLD:
                    in_pick_vertical = True
                    maximum_acceleration_vertical = abs(vertical)
                    last_vertical_pick_timestamp = timestamp
                    ksigma_vertical_at_pick = ksigma_vertical
                    logging.info('Vertical pick at %s ksigma=%s',timestamp,ksigma_vertical_at_pick)
            if in_pick_horizontal:
                if ksigma_horizontal < ksigma_horizontal_at_pick:
                    self.recent_picks.append((last_horizontal_pick_timestamp, [maximum_acceleration_north, maximum_acceleration_east, 0.0]))
                    while len(self.recent_picks) > RECENT_PICKS_COUNT:
                        self.recent_picks = self.recent_picks[1:]
                    self.send_event(last_horizontal_pick_timestamp, [maximum_acceleration_north, maximum_acceleration_east, 0.0])
                    in_pick_horizontal = False
                else:
                    if abs(north) > maximum_acceleration_north:
                        maximum_acceleration_north = abs(north)
                    if abs(east) > maximum_acceleration_east:
                        maximum_acceleration_east = abs(east)
            if in_pick_vertical:
                if ksigma_vertical < ksigma_vertical_at_pick:
                    self.recent_picks.append((last_vertical_pick_timestamp, [0.0, 0.0, maximum_acceleration_vertical]))
                    while len(self.recent_picks) > RECENT_PICKS_COUNT:
                        self.recent_picks = self.recent_picks[1:]
                    # pick has ended: send the message
                    self.send_event(last_vertical_pick_timestamp, [0.0, 0.0, maximum_acceleration_vertical])                   
                    in_pick_vertical = False 
                else:
                    if abs(vertical) > maximum_acceleration_vertical:
                        maximum_acceleration_vertical = abs(vertical)
                                               
            

            vertical_accelerations = vertical_accelerations[1:]
            horizontal_accelerations = horizontal_accelerations[1:]   



    def DisplayDeviceInfo(self):
            print("|------------|----------------------------------|--------------|------------|")
            print("|- Attached -|-              Type              -|- Serial No. -|-  Version -|")
            print("|------------|----------------------------------|--------------|------------|")
            print("|- %8s -|- %30s -|- %10d -|- %8d -|" % (self.accelerometer.isAttached(), self.accelerometer.getDeviceName(), self.accelerometer.getSerialNum(), self.accelerometer.getDeviceVersion()))
            print("|------------|----------------------------------|--------------|------------|")
            print("Number of Axes: %i" % (self.accelerometer.getAccelerationAxisCount()))
            print('Max Acceleration Axis 0: {} Min Acceleration Axis 0: {}'.format(self.accelerometer.getAccelerationMax(0), self.accelerometer.getAccelerationMin(0)))
            print('Max Acceleration Axis 1: {} Min Acceleration Axis 1: {}'.format(self.accelerometer.getAccelerationMax(1), self.accelerometer.getAccelerationMin(1)))
            print('Max Acceleration Axis 2: {} Min Acceleration Axis 2: {}'.format(self.accelerometer.getAccelerationMax(2), self.accelerometer.getAccelerationMin(2)))
    

    def setFileStoreInterval(self, file_store_interval):
        # sets the interval for writing the data to a new file
        self.file_store_interval = file_store_interval
    
    #Event Handler Callback Functions
    def AccelerometerAttached(self, e):
        attached = e.device
        logging.info("Accelerometer %s Attached!", attached.getSerialNum())

    
    def AccelerometerDetached(self, e):
        detached = e.device
        self.phidget_attached = False
        logging.warn('Accelerometer %s Detached!',(detached.getSerialNum()))
            
    def AccelerometerError(self, e):
        try:
            source = e.device
            print("Accelerometer %i: Phidget Error %i: %s" % (source.getSerialNum(), e.eCode, e.description))
        except PhidgetException as e:
            print("Phidget Exception %i: %s" % (e.code, e.details))  
            
    def AccelerometerAccelerationChanged(self, e):
        source = e.device
        print("Accelerometer %i: Axis %i: %6f" % (source.getSerialNum(), e.index, e.acceleration))

    def MakeFilename(self, timestamp):
        return self.datastore + '/' + str(self.accelerometer.getSerialNum()) + '_' + timestamp.strftime(FILESTORE_NAMING) + '.dat'

    def setTimingFitVariables(self, base_time, gradient, intercept):
        # this is called by the main client which is monitoring the system clock compared with NTP
        with self.timing_lock:
            self.timing_base_time = base_time
            self.timing_gradient = gradient
            self.timing_intercept = intercept


    def GetNtpCorrectedTimestamp(self):
        # from the current system time we use the NTP thread's line fit to estimate the true time
        time_now = datetime.datetime.utcnow()
        offset_estimate = (time_now-self.timing_base_time).total_seconds() * self.timing_gradient + self.timing_intercept       
        return time_now + datetime.timedelta(microseconds = offset_estimate*1000000.0)


    def SpatialData(self, e):
        if not self.phidget_attached:
            return
        
        sample_timestamp = self.GetNtpCorrectedTimestamp()
        
        if self.time_start == None:
            self.time_start = sample_timestamp
            
            self.last_sample_datetime = self.time_start
            self.sample_count = 0
            self.accelerations = []
            if self.datastore:
                self.datastore_filename = self.MakeFilename(sample_timestamp)
                logging.info('Storing samples to %s',self.datastore_filename)
                self.datastore_file = open(self.datastore_filename, 'w')
                self.first_sample_timestamp_in_file = None
            self.last_phidgets_timestamp = 0.0
            
        for index, spatialData in enumerate(e.spatialData):
            phidgets_timestamp = spatialData.Timestamp.seconds + (spatialData.Timestamp.microSeconds * 0.000001)
            # the accelerations are scaled and reordered to conform to the SAF standard of [N, E, Z]
            accs = [PHIDGETS_ACCELERATION_TO_G*spatialData.Acceleration[1],\
                    PHIDGETS_ACCELERATION_TO_G*spatialData.Acceleration[0],\
                    PHIDGETS_ACCELERATION_TO_G*spatialData.Acceleration[2]]
            #accs = [a*PHIDGETS_ACCELERATION_TO_G for a in spatialData.Acceleration] 
            #print spatialData.Acceleration
            #print accs
            if len(self.accelerations) == 0:
                self.accelerations = accs
            else:
                for i in range(len(self.accelerations)):
                    self.accelerations[i] += accs[i]
            
            if self.last_phidgets_timestamp:
                if phidgets_timestamp - self.last_phidgets_timestamp > 1.5 * PHIDGETS_NOMINAL_DATA_INTERVAL_MS:
                    logging.warn('Missing samples: last sample %s current sample %s equiv samples %s',\
                                 self.last_phidgets_timestamp, phidgets_timestamp, \
                                 (phidgets_timestamp-self.last_phidgets_timestamp)/PHIDGETS_NOMINAL_DATA_INTERVAL_MS)
                
            self.last_phidgets_timestamp = phidgets_timestamp
                       
            self.last_sample_datetime = sample_timestamp
           
            self.sample_count += 1
            
            if self.sample_count == PHIDGETS_DECIMATION:
               
                # we average the last PHIDGETS_DECIMATION samples
                 
                accelerations = [acc / float(PHIDGETS_DECIMATION) for acc in self.accelerations]
                
                #invert channel 1 (E-W) - this results in +1g being reported when the sensor is resting on its E side
                accelerations[1] = -accelerations[1]
                
                data_entry = [sample_timestamp, accelerations]
                
                # put this reading in the queue for the Picker
                self.sensor_readings_queue.put(data_entry)
                
                self.data_buffer.append(data_entry)
                
                if self.datastore_file:
                    if self.first_sample_timestamp_in_file == None:
                        self.first_sample_timestamp_in_file = sample_timestamp
                    self.datastore_file.write(sample_timestamp.strftime(PRECISION_NAMING) + ' ' +
                                              ' '.join("%10.7f" % x for x in accelerations)+'\n')

            
                self.sample_count = 0
                self.accelerations = []
        
                if sample_timestamp - self.first_sample_timestamp_in_file >= self.file_store_interval:
                    logging.info('File store interval elapsed with %s samples, rate %s samples/second',len(self.data_buffer),float(len(self.data_buffer))/self.file_store_interval.seconds)
                    if self.datastore:
                        # we will change to a new file in the datastore
                        self.datastore_file.close()
                        self.last_datastore_filename = self.datastore_filename
                        
                    self.data_buffer = []
                    self.time_start = None  

                   

    def to_dict(self):
        # No need to persist anything that doesn't change.
        details = {}
        details['module'] = 'PhidgetsSensor'
        details['class'] = 'Sensor'
        with self.sensor_data_lock:
            details['sensor_id'] = self.sensor_data.sensor_id
            details['serial'] = self.sensor_data.serial
        details['datastore'] = self.datastore
        if self.last_datastore_filename_uploaded:
            details['last_upload'] = self.last_datastore_filename_uploaded
        else:
            details['last_upload'] = ''
        if self.time_server:
            details['time_server'] = self.time_server
            
        
        return details

    def get_metadata(self):
        data_copy = client_messages_pb2.SensorMetadata()
        with self.sensor_data_lock:
            data_copy.CopyFrom(self.sensor_data)
        return data_copy
    
    def datafiles_not_yet_uploaded(self):
        # Returns a list of files that are older than last_datastore_filename (or current time) in the
        # data file directory that have not yet been uploaded
        # we subtract 10 minutes off the time to avoid finding the currently open file (although we could in 
        # principle trap that)
        
        file_list = []
        last_file_date = self.GetNtpCorrectedTimestamp() - datetime.timedelta(seconds=600)
            
        logging.info('Searching for files older than %s',last_file_date)
        for f in os.listdir(self.datastore):
            filename = self.datastore + '/' + f
            if filename == self.datastore_filename:
                logging.info('Will not add currently opened file %s', filename)
                continue
            if os.path.isfile(filename):
                    try:
                        t = os.path.getctime(filename)
                        file_date = datetime.datetime.fromtimestamp(t)
                        if file_date < last_file_date:
                            logging.info('Not yet uploaded: %s',filename)
                            file_list.append(filename)
                    except:
                        logging.error('Error getting file time for %s', filename)
                
        return file_list
   
    def datafile_to_streams(self, filename):

        # opens the datafile, reads the accelerometer readings, and adjusts the samples to match
        # the required delta time interval.
        # Places the adjusted samples in the returned serialized DataRecord object
        
        data = heartbeat_pb2.DataRecord()
        data.datapoint_spacing = PHIDGETS_RESAMPLED_DATA_INTERVAL_MS

        with open(filename,'r') as f:
            lines = f.readlines()
         
        # the time stamp of the first entry in the file   
        first_entry = lines[0].split()
        first_entry_time = datetime.datetime.strptime(first_entry[0], PRECISION_NAMING)
        
        start_time = first_entry_time
        
        # the time stamp of the last entry
        last_entry = lines[-1].split()
        last_entry_time = datetime.datetime.strptime(last_entry[0], PRECISION_NAMING)
               
        delta_step_seconds = PHIDGETS_RESAMPLED_DATA_INTERVAL_MS * 0.001
        
        # given the first and last entries, we calculate the number of steps of delta interval to span the difference
        num_steps = 1 + int(round((last_entry_time - first_entry_time).total_seconds() / delta_step_seconds))

        # we initialise our three acceleration component arrays each of length num_steps to "None"        
        streams_values = [None,None,None]
        for i in range(3):
            streams_values[i] = [None]*num_steps

        # now we read each timestamped line in the file
        for line in lines:
            # each line entry has a NTP corrected timestamp and (typically) 3 acceleration values
            entry = line.split()
                        
            entry_time = datetime.datetime.strptime(entry[0], PRECISION_NAMING)
            
            #we calculate the location (step) of this time stamp in the acceleration array
            step = int(round((entry_time-first_entry_time).total_seconds() / delta_step_seconds))
            if step >= num_steps:
                logging.error('Resampling at step %s line %s',step, line)
                continue
            
            # and we calculate the absolute time of this location (step)
            step_time = first_entry_time + datetime.timedelta(microseconds=delta_step_seconds*step*1000000)
            
            # we calculate the difference between the step's absolute time, and the timestamp in the file
            difference = (step_time-entry_time).total_seconds()
            
            # if the difference is zero (i.e. the timestamp is exactly in the right position) we add the accelerations 
            if difference == 0.0 or step == 0:
                for i in range(3):
                    streams_values[i][step] = float(entry[i+1])
            else:
                # otherwise, we calculate the acceleration at the step by linear interpolation
                # As = d/(d+delta)(A1-A0) + A0
                # where As is the acceleration at the step
                # d is the step interval (seconds)
                # delta is the difference between the step time and the time stamp
                # A1 and A0 are the accelerations at the timestamp and at the previous step, respectively
                
                correction = delta_step_seconds / (delta_step_seconds + difference)
                for i in range(3):
                    this_accel = float(entry[i+1])
                    last_accel = streams_values[i][step-1]
                    if last_accel == None:
                        # missing data for the previous step: assign the current acceleration
                        streams_values[i][step-1] = this_accel
                        last_accel = this_accel
                    streams_values[i][step] = correction * (this_accel-last_accel) + last_accel
       
        # the end time is defined as the start time plus delta times (the number of steps minus one)                
        end_time = start_time + datetime.timedelta(microseconds=delta_step_seconds*(num_steps-1)*1000000)


        #logging.info('File %s %s Samples created %s Start %s End %s',filename,len(lines),num_steps,start_time,end_time)
          
        # there may be positions in the acceleration arrays that are not yet filled in (i.e. == None)
        # if so we assign them to the most recent filled in accelerations
          
        # add the data streams to the message
        for stream_values in streams_values:
            for j in range(1,len(stream_values)):
                if stream_values[j] == None:
                    stream_values[j] = stream_values[j-1]  
            
            data_stream = data.streams.add()
            data_stream.values.extend(stream_values)
            
        data = data.SerializeToString()
        
        return (start_time, end_time, num_steps, data)
  
    def get_filename_data(self, filename):
        # prepares the data in filename into an offer protocol buffer
        # ensure that this is not the file currently being written
        if filename == self.datastore_filename:
            return None, None
        
        offer_pb = heartbeat_pb2.SensorReadingDescription()
        offer_pb.data_format = heartbeat_pb2.SensorReadingDescription.DATA_RECORD
        offer_pb.current_data = True
        offer_pb.sensor_id = self.sensor_data.sensor_id  
        try:
            (start_time, end_time, num_samples, data) = self.datafile_to_streams(filename)
        except Exception,e: 
            logging.error('Error %s converting datafile %s to streams', str(e), filename)
            # move the file to a directory for corrupt files
            self.mark_file_corrupted(filename)
            
            return None, None
              
        logging.info('Data file %s %s elapsed seconds, nsamples %s',filename, (end_time-start_time).total_seconds(), num_samples) 

        offer_pb.start_date = util.date_format(start_time)
        offer_pb.end_date = util.date_format(end_time)
        return offer_pb, data
      

    def get_current_data(self):
        offer_pb = heartbeat_pb2.SensorReadingDescription()
        offer_pb.data_format = heartbeat_pb2.SensorReadingDescription.DATA_RECORD
        offer_pb.current_data = True
        offer_pb.sensor_id = self.sensor_data.sensor_id
        
        # we will use the latest data stored to file
        #self.last_datastore_filename = 'D:/phidget/367018_20150106T235801.dat'
        if not self.last_datastore_filename:
            logging.info('No latest file in datastore to upload')
            return None, None, None
        
        (start_time, end_time, num_samples, data) = self.datafile_to_streams(self.last_datastore_filename)
              
        logging.info('Latest data file %s with data from %s to %s %s elapsed seconds number samples %s',self.last_datastore_filename, start_time, end_time, (end_time-start_time).total_seconds(), num_samples) 
        
        offer_pb.start_date = util.date_format(start_time)
        offer_pb.end_date = util.date_format(end_time)
        return offer_pb, data, self.last_datastore_filename
    
    def mark_file_uploaded(self, filename):
        # when a sensor data file has been successfully uploaded to the server we move it to the uploaded directory
        try:
            os.makedirs(self.datastore_uploaded)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                logging.error('Error making directory %s', self.datastore_uploaded)
        try:            
            shutil.copy2(filename, self.datastore_uploaded)
            self.last_datastore_filename_uploaded = filename
            os.remove(filename)
        except:
            logging.warning('Failed to move %s to %s', filename, self.datastore_uploaded)
        
    def mark_file_corrupted(self, filename):
        # when a sensor data file fails to convert to streams we move it to the corrupt directory
        try:
            os.makedirs(self.datastore_corrupted)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise
        try:            
            shutil.copy2(filename, self.datastore_corrupted)
        except:
            logging.warning('Failed to move %s to %s', filename, self.datastore_corrupted)
        # always remove the corrupt file from the main directory  
        try:     
            os.remove(filename)
        except:
            logging.error('Failed to delete %s', filename)
            
        

    def set_sensor_id(self, sensor_id):
        with self.sensor_data_lock:
            self.sensor_data.sensor_id = sensor_id

    def run(self, shutdown_event):
        from random import Random
        random = Random()
        random.seed()
        wait_time = random.random() * RANDOM_WAIT_TIME + MINIMUM_WAIT_TIME
        while not shutdown_event.is_set():
            if not shutdown_event.wait(timeout=wait_time):
                # for now we will just send random picks
                self.send_event(util.system_time(),
                                [random.random() for _ in range(3)])
                wait_time = random.random() * 10 + 2
        logging.info('Shutting down.')

    def send_event(self, event_time, values):
        if not self.sensor_data.HasField('sensor_id'):
            logging.error('Cannot send an event without a sensor_id')
            return
        self._send_event(self.sensor_data.sensor_id, event_time, values)

    def _send_event(self, sensor_id, event_time, values):
        raise RuntimeError('Cannot send events without a function passed from '
                           'the Client.')

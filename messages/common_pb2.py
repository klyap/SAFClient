# Generated by the protocol buffer compiler.  DO NOT EDIT!

from google.protobuf import descriptor
from google.protobuf import message
from google.protobuf import reflection
from google.protobuf import descriptor_pb2
# @@protoc_insertion_point(imports)



DESCRIPTOR = descriptor.FileDescriptor(
  name='common.proto',
  package='saf',
  serialized_pb='\n\x0c\x63ommon.proto\x12\x03saf\"F\n\x0f\x43lientSignature\x12\x0c\n\x04\x64\x61te\x18\x01 \x01(\t\x12\x12\n\nmessage_id\x18\x02 \x01(\r\x12\x11\n\tsignature\x18\x03 \x01(\t\"?\n\rStatusMessage\x12\x1d\n\x04type\x18\x01 \x01(\x0e\x32\x0f.saf.StatusType\x12\x0f\n\x07message\x18\x02 \x01(\t\"5\n\x0fGenericResponse\x12\"\n\x06status\x18\x01 \x01(\x0b\x32\x12.saf.StatusMessage*\xfd\x01\n\nStatusType\x12\x0b\n\x07SUCCESS\x10\x00\x12\x11\n\rUNKNOWN_ERROR\x10\x01\x12\x13\n\x0fINVALID_REQUEST\x10\x02\x12\x12\n\x0eUNKNOWN_CLIENT\x10\x03\x12\x12\n\x0eUNKNOWN_SENSOR\x10\x04\x12\x13\n\x0f\x44\x41TASTORE_ERROR\x10\x05\x12\x15\n\x11\x44\x45\x41\x44LINE_EXCEEDED\x10\x06\x12\x14\n\x10OVER_QUOTA_ERROR\x10\x07\x12\x12\n\x0e\x44OS_API_DENIAL\x10\x08\x12\x12\n\x0eSERVER_TIMEOUT\x10\t\x12\x12\n\x0ePATH_NOT_FOUND\x10\n\x12\x14\n\x10NAME_UNAVAILABLE\x10\x0f*\xc5\x01\n\nSensorType\x12\x18\n\x14\x41\x43\x43\x45LEROMETER_3_AXIS\x10\x00\x12\x18\n\x14\x41\x43\x43\x45LEROMETER_1_AXIS\x10\x01\x12\x0f\n\x0bTEMPERATURE\x10\x02\x12\x0c\n\x08PRESSURE\x10\x03\x12\x0c\n\x08HUMIDITY\x10\x04\x12\x0b\n\x07OPTICAL\x10\x05\x12\x10\n\x0cPHOTOVOLTAIC\x10\x06\x12\x07\n\x03\x43H4\x10\x07\x12\x07\n\x03LPG\x10\x08\x12\x06\n\x02\x43O\x10\t\x12\x06\n\x02H2\x10\n\x12\n\n\x06GEIGER\x10\x0b\x12\t\n\x05OTHER\x10@*]\n\x12LocationSourceType\x12\x0e\n\nUSER_INPUT\x10\x00\x12\x08\n\x04\x43\x45LL\x10\x01\x12\x07\n\x03GPS\x10\x02\x12\x08\n\x04WIFI\x10\x03\x12\x06\n\x02IP\x10\x04\x12\x12\n\x0eSERVER_DEFAULT\x10@B\"\n\x18\x65\x64u.caltech.saf.messagesB\x06\x43ommon')

_STATUSTYPE = descriptor.EnumDescriptor(
  name='StatusType',
  full_name='saf.StatusType',
  filename=None,
  file=DESCRIPTOR,
  values=[
    descriptor.EnumValueDescriptor(
      name='SUCCESS', index=0, number=0,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='UNKNOWN_ERROR', index=1, number=1,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='INVALID_REQUEST', index=2, number=2,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='UNKNOWN_CLIENT', index=3, number=3,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='UNKNOWN_SENSOR', index=4, number=4,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='DATASTORE_ERROR', index=5, number=5,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='DEADLINE_EXCEEDED', index=6, number=6,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='OVER_QUOTA_ERROR', index=7, number=7,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='DOS_API_DENIAL', index=8, number=8,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='SERVER_TIMEOUT', index=9, number=9,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='PATH_NOT_FOUND', index=10, number=10,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='NAME_UNAVAILABLE', index=11, number=15,
      options=None,
      type=None),
  ],
  containing_type=None,
  options=None,
  serialized_start=214,
  serialized_end=467,
)


_SENSORTYPE = descriptor.EnumDescriptor(
  name='SensorType',
  full_name='saf.SensorType',
  filename=None,
  file=DESCRIPTOR,
  values=[
    descriptor.EnumValueDescriptor(
      name='ACCELEROMETER_3_AXIS', index=0, number=0,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='ACCELEROMETER_1_AXIS', index=1, number=1,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='TEMPERATURE', index=2, number=2,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='PRESSURE', index=3, number=3,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='HUMIDITY', index=4, number=4,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='OPTICAL', index=5, number=5,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='PHOTOVOLTAIC', index=6, number=6,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='CH4', index=7, number=7,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='LPG', index=8, number=8,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='CO', index=9, number=9,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='H2', index=10, number=10,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='GEIGER', index=11, number=11,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='OTHER', index=12, number=64,
      options=None,
      type=None),
  ],
  containing_type=None,
  options=None,
  serialized_start=470,
  serialized_end=667,
)


_LOCATIONSOURCETYPE = descriptor.EnumDescriptor(
  name='LocationSourceType',
  full_name='saf.LocationSourceType',
  filename=None,
  file=DESCRIPTOR,
  values=[
    descriptor.EnumValueDescriptor(
      name='USER_INPUT', index=0, number=0,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='CELL', index=1, number=1,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='GPS', index=2, number=2,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='WIFI', index=3, number=3,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='IP', index=4, number=4,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='SERVER_DEFAULT', index=5, number=64,
      options=None,
      type=None),
  ],
  containing_type=None,
  options=None,
  serialized_start=669,
  serialized_end=762,
)


SUCCESS = 0
UNKNOWN_ERROR = 1
INVALID_REQUEST = 2
UNKNOWN_CLIENT = 3
UNKNOWN_SENSOR = 4
DATASTORE_ERROR = 5
DEADLINE_EXCEEDED = 6
OVER_QUOTA_ERROR = 7
DOS_API_DENIAL = 8
SERVER_TIMEOUT = 9
PATH_NOT_FOUND = 10
NAME_UNAVAILABLE = 15
ACCELEROMETER_3_AXIS = 0
ACCELEROMETER_1_AXIS = 1
TEMPERATURE = 2
PRESSURE = 3
HUMIDITY = 4
OPTICAL = 5
PHOTOVOLTAIC = 6
CH4 = 7
LPG = 8
CO = 9
H2 = 10
GEIGER = 11
OTHER = 64
USER_INPUT = 0
CELL = 1
GPS = 2
WIFI = 3
IP = 4
SERVER_DEFAULT = 64



_CLIENTSIGNATURE = descriptor.Descriptor(
  name='ClientSignature',
  full_name='saf.ClientSignature',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    descriptor.FieldDescriptor(
      name='date', full_name='saf.ClientSignature.date', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=unicode("", "utf-8"),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    descriptor.FieldDescriptor(
      name='message_id', full_name='saf.ClientSignature.message_id', index=1,
      number=2, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    descriptor.FieldDescriptor(
      name='signature', full_name='saf.ClientSignature.signature', index=2,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=unicode("", "utf-8"),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  options=None,
  is_extendable=False,
  extension_ranges=[],
  serialized_start=21,
  serialized_end=91,
)


_STATUSMESSAGE = descriptor.Descriptor(
  name='StatusMessage',
  full_name='saf.StatusMessage',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    descriptor.FieldDescriptor(
      name='type', full_name='saf.StatusMessage.type', index=0,
      number=1, type=14, cpp_type=8, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    descriptor.FieldDescriptor(
      name='message', full_name='saf.StatusMessage.message', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=unicode("", "utf-8"),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  options=None,
  is_extendable=False,
  extension_ranges=[],
  serialized_start=93,
  serialized_end=156,
)


_GENERICRESPONSE = descriptor.Descriptor(
  name='GenericResponse',
  full_name='saf.GenericResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    descriptor.FieldDescriptor(
      name='status', full_name='saf.GenericResponse.status', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  options=None,
  is_extendable=False,
  extension_ranges=[],
  serialized_start=158,
  serialized_end=211,
)

_STATUSMESSAGE.fields_by_name['type'].enum_type = _STATUSTYPE
_GENERICRESPONSE.fields_by_name['status'].message_type = _STATUSMESSAGE
DESCRIPTOR.message_types_by_name['ClientSignature'] = _CLIENTSIGNATURE
DESCRIPTOR.message_types_by_name['StatusMessage'] = _STATUSMESSAGE
DESCRIPTOR.message_types_by_name['GenericResponse'] = _GENERICRESPONSE

class ClientSignature(message.Message):
  __metaclass__ = reflection.GeneratedProtocolMessageType
  DESCRIPTOR = _CLIENTSIGNATURE
  
  # @@protoc_insertion_point(class_scope:saf.ClientSignature)

class StatusMessage(message.Message):
  __metaclass__ = reflection.GeneratedProtocolMessageType
  DESCRIPTOR = _STATUSMESSAGE
  
  # @@protoc_insertion_point(class_scope:saf.StatusMessage)

class GenericResponse(message.Message):
  __metaclass__ = reflection.GeneratedProtocolMessageType
  DESCRIPTOR = _GENERICRESPONSE
  
  # @@protoc_insertion_point(class_scope:saf.GenericResponse)

# @@protoc_insertion_point(module_scope)

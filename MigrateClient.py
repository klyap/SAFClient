'''
Created on Mar 2, 2015

@author: Julian
'''

import os
import sys
from string import Template

# Note: old client is stopped by: /etc/init.d/csnd stop
# Note: old client has its settings in /etc/CSNClientSettings
"""
id: use52
version: 2.4
cloudId: 6572938060890112
cloudSecret: e3f58175c118c51267cc4fa2fcaf6132e7d48b66d6eb827e73491aa6037b0dc7
cloudMessageId: 77797
updatePeriod: 60
lastModified: 1399078458
pickParamsZ: 10.000000 0.500000 1.000000 1.500000
pickParamsNE: 10.000000 0.500000 1.000000 1.500000
heartbeatPeriod: 10
ringLength: 1440
requisitions: 
timeServers: ntp-02.caltech.edu
webServerURLRoot: http://csn.cacr.caltech.edu
cloudURLRoot: http://csn-server.appspot.com/api/v1/csn
datagramServer: csn.cacr.caltech.edu
location: 34.136420,-118.128350,1
"""

YAML_TEMPLATE = """
name:                 ${name}
client_id:            ${cloudId}
client_secret:        !!python/unicode '${cloudSecret}'
message_id:           ${cloudMessageId}
building:             unknown
floor:                '1'
latitude:             ${latitude}
longitude:            ${longitude}
location_source_type: 0  # common_pb2.USER_INPUT
location_description: Virtual
mobility_type:        1  # client_messages_pb2.ClientMetadata.DESKTOP
sensors:
    - module:              PhidgetsSensor
      class:               Sensor
      sensor_id:           0
      datastore:           !!python/unicode '/tmp/phidgetsdata'
      last_upload:         !!python/unicode ''
      time_server:         'ntp-02.caltech.edu'
server:               csn-server.appspot.com
namespace:            csn 
software_version:     SAFCSNclient v1.0
"""

OLD_CLIENT_FILE = '/etc/CSNClientSettings'
NEW_CLIENT_FILE = 'CSN_client.yaml'

def main():
    
    stop_command = '/etc/init.d/csnd stop'
    print 'Stopping old client with:', stop_command
    try:
        os.system(stop_command)
    except:
        print 'Error executing stop command: migration will halt'
        sys.exit(0)

    rename_command = 'mv /etc/init.d/csnd /etc/init.d/csnd.disabled'
    print 'Renaming daemon with:', rename_command
    try:
        os.system(rename_command)
    except:
        print 'Error executing rename command: migration will halt'
        sys.exit(0)
        
    client_details = {}    
    try:
        for line in open(OLD_CLIENT_FILE,'r'):
            tokens = line.split()
            if tokens[0] == 'id:':
                client_details['legacy_id'] = tokens[1]
            elif tokens[0] == 'name:':
                client_details['name'] = tokens[1]
            elif tokens[0] == 'cloudId:':
                client_details['cloudId'] = tokens[1]
            elif tokens[0] == 'cloudSecret:':
                client_details['cloudSecret'] = tokens[1]
            elif tokens[0] == 'cloudMessageId:':
                client_details['cloudMessageId'] = tokens[1]
            elif tokens[0] == 'location:':
                lat, lon, _ = tokens[1].split(',')
                client_details['latitude'] = lat
                client_details['longitude'] = lon
            
    except:
        print 'Error reading',OLD_CLIENT_FILE,': migration will halt'
        sys.exit(0)
    
    yaml_values = {'name': client_details['name'], 
                   'cloudId': client_details['cloudId'], 
                   'cloudSecret': client_details['cloudSecret'],
                   'cloudMessageId': client_details['cloudMessageId'],
                   'latitude': client_details['latitude'],
                   'longitude': client_details['longitude']}
        
    yaml_to_write = Template(YAML_TEMPLATE).safe_substitute(yaml_values)

    new_file = open(NEW_CLIENT_FILE,'w')
    new_file.write(yaml_to_write)
    new_file.close()
    
    print NEW_CLIENT_FILE,'written with \n',yaml_to_write
    

if __name__ == '__main__':
    main()
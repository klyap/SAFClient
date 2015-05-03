'''
Created on August 6, 2013

@author: Julian
'''
import os
import sys
import time
import datetime
import threading
import logging
import logging.handlers
import random
import Queue
import ntplib
import numpy
from time import ctime

from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer
import urlparse

import client
from GetDiskUsage import disk_usage

from messages import heartbeat_pb2


LOGFILE = 'PyCSN.log'
 


TARGET_SERVER = 'csn-server.appspot.com'
TARGET_NAMESPACE = 'csn'
TIME_SERVERS = ["ntp-02.caltech.edu","0.us.pool.ntp.org","1.us.pool.ntp.org","2.us.pool.ntp.org","3.us.pool.ntp.org"]


HEARTBEAT_INTERVAL = datetime.timedelta(seconds=600)
NTP_INTERVAL = datetime.timedelta(seconds=60)
STORAGE_CHECK_INTERVAL = datetime.timedelta(seconds=3600)

MIN_POINTS_TIME_FIT = 10
MAX_POINTS_TIME_FIT = 60

PERCENT_STORAGE_USED_THRESHOLD = 90.0

PORT_NUMBER=9000


STATION = 'CSN_client'


queue = Queue.Queue()


heartbeats = True
ntp = True
web = True
check_storage = True

class PyCSN(object):

    def webServerThread(self):
        try:
            #Create a web server and define the handler to manage the
            #incoming request
            server = HTTPServer(('', PORT_NUMBER), PyCSNWebServer)
    
            #Wait forever for incoming http requests
            while web:
                server.handle_request()
                
        except Exception, errtxt:
            server.socket.close()
            raise sys.exit(errtxt)
        
        server.close()
        logging.warn('Web server terminated')   
        

    def ntpThread(self):
        ntp_client = ntplib.NTPClient()
        # we start off needing to accumulate points for the line fit quickly
        startup_seconds = 1
        ntp_interval = datetime.timedelta(seconds=startup_seconds)
        
        line_fit_m = 0.0
        line_fit_c = 0.0
        
        x_points = []
        y_points = []
        
        base_time = datetime.datetime.utcnow()
        start_time = base_time
        while ntp:
            if ntp_interval < NTP_INTERVAL:
                startup_seconds += 2
                ntp_interval = datetime.timedelta(seconds=startup_seconds)
            else:
                ntp_interval = ntp_interval
                
            response = None
            
            for time_server in self.time_servers:
                try:
                    start_time = datetime.datetime.utcnow()
                    response = ntp_client.request(time_server, version=3)
                    break
                except:
                    logging.warn('NTP: No response from %s',time_server)
                    
            if response: 
                # add a point to the line for fitting
                diff_epoch = (start_time-base_time).total_seconds() 
                x_points.append(diff_epoch)
                y_points.append(response.offset)
                
                if len(x_points) > MIN_POINTS_TIME_FIT:
                    while len(x_points) > MAX_POINTS_TIME_FIT:
                        x_points = x_points[1:]
                        y_points = y_points[1:]
                    
                    # get the current estimate
                    offset_estimate = diff_epoch*line_fit_m + line_fit_c
                    logging.info('Time server %s Offset %10.6f Estimate %10.6f Error %8.6fs',\
                                 time_server,response.offset,offset_estimate,response.offset-offset_estimate)
                    
                    # do the line fit to solve for y = mx+c
                    x_mean = numpy.mean(x_points)
                    y_mean = numpy.mean(y_points)
                    sum_xy = 0.0
                    sum_x2 = 0.0
                    for x,y in zip(x_points, y_points):
                        sum_xy += (x-x_mean)*(y-y_mean)
                        sum_x2 += (x-x_mean)*(x-x_mean)
                    line_fit_m = sum_xy / sum_x2
                    line_fit_c = y_mean - (line_fit_m*x_mean)
                    
                    #logging.info('Time interval %s Line fit m, c %s %s %s points',\
                    #             ntp_interval,line_fit_m, line_fit_c,len(x_points))   
                                   
                for sensor_id, (sensor, stats) in self.phidgetClient.sensors.viewitems():
                    sensor.setTimingFitVariables(base_time, line_fit_m, line_fit_c)
             
            elapsed = datetime.datetime.utcnow() - start_time
            if ntp_interval > elapsed:
                time.sleep((ntp_interval-elapsed).total_seconds()) 
        logging.warn('NTP thread terminated')   

    def storageThread(self):
        # this thread periodically checks the storage space available in the Sensor's data directory,
        # and cleans out older files when the storage space becomes more full than a threshold
        while(check_storage):
            if self.phidgetClient:
                for sensor_id, (sensor, stats) in self.phidgetClient.sensors.viewitems():
                    if sensor.datastore_corrupted:
                        # remove corrupted (unparseable) data files
                        for filename in os.listdir(sensor.datastore_corrupted):
                            fullname = os.path.join(sensor.datastore_corrupted, filename)
                            if os.path.isfile(fullname):
                                try:
                                    os.remove(fullname)
                                    logging.info('Storage cleanup, removed %s', fullname)
                                except:
                                    logging.warn('Exception removing file %s', fullname)
                                
                    if sensor.datastore_uploaded:
                        usage = disk_usage(sensor.datastore_uploaded)
                        percent = 100. * float(usage.used) / float(usage.total)
                        logging.info('%s%% used storage', percent)
                    
                        if percent > PERCENT_STORAGE_USED_THRESHOLD:
                            # remove oldest files from corrupted and uploaded directories
                            while percent > PERCENT_STORAGE_USED_THRESHOLD:
                                files = os.listdir(sensor.datastore_uploaded)
                                if len(files) <= 0:
                                    logging.info('No more files in %s to remove', sensor.datastore_uploaded)
                                    break
                                files.sort(key=lambda x: os.path.getmtime(os.path.join(sensor.datastore_uploaded,x)))
                                fullname = os.path.join(sensor.datastore_uploaded,files[0])
                                if not os.path.isfile(fullname):
                                    logging.error('Unexpected %s', fullname)
                                    break 
                                try:
                                    os.remove(fullname)
                                    logging.info('Storage cleanup, removed %s', fullname)
                                except:
                                    logging.warn('Exception removing file %s', fullname)
                                    break
                                usage = disk_usage(sensor.datastore_uploaded)
                                percent = 100. * float(usage.used) / float(usage.total)
                        logging.info('Finished storage cleaning, percent usage now %s', percent)               
                        
                time.sleep(STORAGE_CHECK_INTERVAL.total_seconds())
        return
    
    def heartbeatThread(self):
        
        while(heartbeats):
            start_time = datetime.datetime.utcnow()
            if self.phidgetClient:
                try:
                    logging.info('Sending heartbeat')
                    self.phidgetClient.send_heartbeat()
                    logging.info('Heartbeat sent for client %s', self.phidgetClient.client_id)
                except IOError, e:
                    logging.error("IO Error on heartbeat %s %s", e.errno, e)
                except:
                    logging.error('Unexpected error on send_heartbeat %s', sys.exc_info()[0])
                try:          
                    self.phidgetClient.to_file(STATION + '.yaml')  
                except:
                    logging.error('Unexpected error writing new YAML file %s', sys.exc_info()[0])
            elapsed = datetime.datetime.utcnow() - start_time
            #print 'Finished sending heartbeats after ',elapsed
            if HEARTBEAT_INTERVAL > elapsed:
                time.sleep((HEARTBEAT_INTERVAL-elapsed).total_seconds())
        logging.warn('Heartbeat thread terminating')
        self.sendHeartbeatQuits()
     
    def sendHeartbeatQuits(self):
        logging.info('Sending heartbeat quit message')
        if not self.phidgetClient:
            return
        self.phidgetClient.send_heartbeat(status_change=heartbeat_pb2.HeartbeatMessage.QUIT)           
        self.phidgetClient.to_file(STATION + '.yaml')  


    def GetLatestSamples(self):
        for sensor_id, (sensor, stats) in self.phidgetClient.sensors.viewitems():
            return list(sensor.data_buffer)
        return None

    def GetRecentPicks(self):
        for sensor_id, (sensor, stats) in self.phidgetClient.sensors.viewitems():
            return list(sensor.recent_picks)
        return None
    
    def SendClientUpdate(self):
        logging.info('Request will be sent to update client %s', self.phidgetClient.client_id)
         
        self.phidgetClient.delta_fields.add('building')
        self.phidgetClient.delta_fields.add('name')
        self.phidgetClient.delta_fields.add('floor')
        
        # We null out the "cacr.id", which is a field used by the old (Leif) client
        self.phidgetClient.add_key_value('cacr.id', '', 'string_value')

              
        (lat, lon) = (self.phidgetClient.client_data.latitude, self.phidgetClient.client_data.longitude)
        try:
            self.phidgetClient.change_location((lat,lon))
            self.phidgetClient.send_update()
        except:
            logging.error('Error sending client update')


       
    
    def __init__(self):
        
        print 'PyCSN Starting!'
        
        log = logging.getLogger('')
        log.setLevel(logging.INFO)
        
        format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        
        fh = logging.handlers.RotatingFileHandler(LOGFILE, maxBytes=600000, backupCount=1)
        fh.setFormatter(format)
        log.addHandler(fh)        

        #ch = logging.StreamHandler(sys.stdout)
        #ch.setFormatter(format)
        #log.addHandler(ch)
        
        logging.info("Instantiate client for Station %s", STATION) 
           
        self.stationFile = STATION + '.yaml'
        self.phidgetClient = client.Client.from_file(self.stationFile)
        
        self.time_servers = TIME_SERVERS
        
        if len(self.phidgetClient.sensors.viewitems()) == 0:
            logging.error("Client has no sensors")
            return
        
        for sensor_id, (sensor, stats) in self.phidgetClient.sensors.viewitems():
            logging.info('Client has Sensor %s',sensor_id)
            if not sensor.phidget_attached:
                raise sys.exit('Phidget not attached - abort')                
            else:    
                sensor.setFileStoreInterval(HEARTBEAT_INTERVAL) 
            if sensor.time_server != None:
                if sensor.time_server not in self.time_servers:
                    self.time_servers = [sensor.time_server] + self.time_servers
                    logging.info("Phidget configuration includes an NTP server, prepended to %s", self.time_servers)

                       
        
        if not self.phidgetClient.client_secret or self.phidgetClient.server != TARGET_SERVER:
                logging.info('Registering new station %s in %s namespace %s',STATION,TARGET_SERVER,TARGET_NAMESPACE)
                try:
                    self.phidgetClient.register(server=TARGET_SERVER, namespace=TARGET_NAMESPACE)
                except Exception, errtxt:
                    raise sys.exit(errtxt)


        # Start by sending a client update, to ensure any changes in the client's yaml are sent to the server
        
        self.SendClientUpdate()
        
        # we start off assuming no clock drift i.e. the adjustment is zero
        
        self.clock_offset = 0.0
        
        logging.info('Starting NTP thread')
        try:
            ntpDaemon = threading.Thread(target=self.ntpThread)
            ntpDaemon.setDaemon(True)
            ntpDaemon.start()
        except Exception, errtxt:
            raise sys.exit(errtxt)
    
        logging.info('Starting heartbeat thread')
        try:
            heartbeatDaemon = threading.Thread(target=self.heartbeatThread)
            heartbeatDaemon.setDaemon(True)
            heartbeatDaemon.start()
        except Exception, errtxt:
            raise sys.exit(errtxt)
        
        logging.info('Starting web server on port %s', PORT_NUMBER)
        try:
            webServerDaemon = threading.Thread(target=self.webServerThread)
            webServerDaemon.setDaemon(True)
            webServerDaemon.start()
        except Exception, errtxt:
            raise sys.exit(errtxt)

        logging.info('Starting storage check thread')
        try:
            storageDaemon = threading.Thread(target=self.storageThread)
            storageDaemon.setDaemon(True)
            storageDaemon.start()
        except Exception, errtxt:
            raise sys.exit(errtxt)
         
    def run(self):

        logging.info('Running ...')
        try:
            health = True
            sleep_time = 10
            while health:
               
                time.sleep(sleep_time)

                for sensor_id, (sensor, _) in self.phidgetClient.sensors.viewitems():
                    if not sensor.phidget_attached or sensor.last_sample_datetime - datetime.datetime.utcnow() > datetime.timedelta(seconds=10):
                        sleep_time *= 2
                        if sleep_time > 36000:
                            logging.warn('Health Check: waited too long for sensor')
                            health = False
                            break                        
                        if not sensor.phidget_attached:
                            logging.warn('Health Check: Sensor %s Not attached. Try to reattach, and wait %s seconds',sensor_id, sleep_time)
                            sensor.StartPhidget()
                        else:
                            logging.warn('Health Check: Sensor %s No samples collected in the last 10 seconds, wait %s seconds',sensor_id,sleep_time)

                    else:
                        sleep_time = 10
                        

                                    
            logging.warn('Main thread terminating')        
        except KeyboardInterrupt:
            logging.warn('Keyboard Interrupt: PyCSN processing terminating')
            
        heartbeats = False
        ntp = False
        web = False
        check_storage = False

        self.sendHeartbeatQuits()
        logging.warn('Exiting')

class PyCSNWebServer(BaseHTTPRequestHandler):

    TIMESTAMP_NAMING = "%Y-%m-%dT%H:%M:%S"
    TIMESTAMP_NAMING_PLOT = "%H:%M:%S"

    #Handler for the GET requests
    def do_GET(self):
        
        global this_client
        
        self.send_response(200)
        self.send_header('Content-type','text/html')
        self.end_headers()
        # Send the html message
        self.wfile.write("<body>")

        self.wfile.write("<h1>CSN Phidgets Client</h1>")

        if self.path == '/update':
            this_client.SendClientUpdate()
            self.wfile.write("Client was updated on the server")
            logging.info('Web server client update request processed')
            return

                            
        E_data = N_data = Z_data = ''
        
        latest_samples = this_client.GetLatestSamples()
        if latest_samples == None:
            self.wfile.write("No Sensor Data available")
            return
        
        num_samples_available = len(latest_samples)
        
        recent_picks = this_client.GetRecentPicks()
        
        #logging.info('Recent picks %s', recent_picks)
        
        num_seconds_to_plot = 120
        
        time_now = datetime.datetime.utcnow()
        time_from = time_now - datetime.timedelta(seconds=num_seconds_to_plot)
               
        num_samples_in_plot = 0
        num_picks_in_plot = 0
        if len(recent_picks) > 0:
            while len(recent_picks) > 0:
                this_pick = recent_picks[0]
                pick_time = this_pick[0]
                pick_accelerations = this_pick[1]
                if pick_time < time_from:
                    recent_picks = recent_picks[1:]
                else:
                    break
        if len(recent_picks) == 0:
            pick_time = None

            
        for sample in latest_samples:
            timestamp = sample[0]
            if timestamp < time_from:
                continue
            if pick_time is not None:
                while pick_time < timestamp:
                    timestamp_string = pick_time.strftime(self.TIMESTAMP_NAMING_PLOT)
                    num_picks_in_plot += 1
                    logging.info('Plot Pick %s %s', pick_time, pick_accelerations)
                    if int(pick_accelerations[2] + 0.5) == 1:
                        Z_data += '["'+timestamp_string+'",'+str(pick_accelerations[2])+', "Pick"],'
                    else:
                        N_data += '["'+timestamp_string+'",'+str(pick_accelerations[0])+', "Pick"],'
                        E_data += '["'+timestamp_string+'",'+str(pick_accelerations[1])+', "Pick"],'
                    recent_picks = recent_picks[1:]                    
                    if len(recent_picks) > 0:
                        this_pick = recent_picks[0]
                        pick_time = this_pick[0]
                        pick_accelerations = this_pick[1]
                    else:
                        pick_time = time_now # false pick beyond limits of plot                        
                    
                    
            #elapsed_seconds = (timestamp - time_from).total_seconds()
            accelerations = sample[1]
            num_samples_in_plot += 1
            timestamp_string = timestamp.strftime(self.TIMESTAMP_NAMING_PLOT)
            E_data += '["'+timestamp_string+'",'+str(accelerations[0])+', null],'
            N_data += '["'+timestamp_string+'",'+str(accelerations[1])+', null],'
            Z_data += '["'+timestamp_string+'",'+str(accelerations[2])+', null],'
            

                
        logging.info('Plotting %s samples and %s picks', num_samples_in_plot, num_picks_in_plot)
                
        self.wfile.write(str(num_samples_in_plot)+" samples and "+str(num_picks_in_plot)+" picks from "+time_from.strftime(self.TIMESTAMP_NAMING)+" (UTC) for "+str(num_seconds_to_plot)+" seconds")         
        
        page_str="""

    <script type="text/javascript" src="https://www.google.com/jsapi"></script>
    <script type="text/javascript">
      google.load("visualization", "1", {packages:["corechart"]});
      google.setOnLoadCallback(drawChart);
      function drawChart() {
        var E_data = new google.visualization.DataTable();
        E_data.addColumn('string','Time');
        E_data.addColumn('number','Acceleration');
        E_data.addColumn({type: 'string', role: 'annotation'});
        E_data.addRows([ %s ]);
        
        var N_data = new google.visualization.DataTable();
        N_data.addColumn('string','Time');
        N_data.addColumn('number','Acceleration');
        N_data.addColumn({type: 'string', role: 'annotation'});
        N_data.addRows([ %s ]);

        var Z_data = new google.visualization.DataTable();
        Z_data.addColumn('string','Time');
        Z_data.addColumn('number','Acceleration');
        Z_data.addColumn({type: 'string', role: 'annotation'});
        Z_data.addRows([ %s ]);

        var E_options = {
          title: 'CSN Phidget Sensor Accelerations: E',
          legend: {position: 'none'},
          hAxis: {title: 'Time', titleTextStyle: {color: 'blue'}, showTextEvery: 500, gridlines: {count: 10}},
          vAxis: {title: 'Acceleration (g)', titleTextStyle: {color: 'blue'}}
        };
        var N_options = {
          title: 'CSN Phidget Sensor Accelerations: N',
          legend: {position: 'none'},
          hAxis: {title: 'Time', titleTextStyle: {color: 'blue'}, showTextEvery: 500 } ,
          vAxis: {title: 'Acceleration (g)', titleTextStyle: {color: 'blue'}}
        };
        var Z_options = {
          title: 'CSN Phidget Sensor Accelerations: Z',
          legend: {position: 'none'},
          annotation: {
            3: {
                style: 'line'
            }
          },
          hAxis: {title: 'Time', titleTextStyle: {color: 'blue'}, showTextEvery: 500},
          vAxis: {title: 'Acceleration (g)', titleTextStyle: {color: 'blue'}}
        };
        
        var E_chart = new google.visualization.LineChart
                (document.getElementById('E_chart_div'));
        var N_chart = new google.visualization.LineChart
                (document.getElementById('N_chart_div'));
        var Z_chart = new google.visualization.LineChart
                (document.getElementById('Z_chart_div'));                
        E_chart.draw(E_data, E_options);
        N_chart.draw(N_data, N_options);
        Z_chart.draw(Z_data, Z_options);
        
      }
    </script>
    <div id="E_chart_div"></div>
    <div id="N_chart_div"></div>
    <div id="Z_chart_div"></div>
    </body>
    """ % (E_data, N_data, Z_data)
        
        self.wfile.write(page_str)
        
        return
        


def main():
    global this_client
    
    #print 'Disk Space Usage',disk_usage(os.getcwd())
    # python -m cProfile -o PyCSNpro.file -s time PyCSN.py
    # python gprof2dot.py -f pstats  PyCSNpro.file > PyCSNpro.dot
    # "C:\Program Files (x86)\Graphviz2.38\bin\dot.exe" -Tpng PyCSNpro.dot > PyCSNpro.png
    
    this_client = PyCSN()
    this_client.run()


if __name__ == '__main__': main()

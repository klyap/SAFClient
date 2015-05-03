#!/bin/sh

# This script installs the new python-based client (developed by Julian Bunn in 2015,
# building on a framework developed by Michael Olson in 2014.
# NOTE:  this script is intended for Debian Lenny systems that lack Python > v2.5.
# *** THERE IS A DIFFERENT SCRIPT FOR Debian Wheezy systems with Python 2.7 available
# as a package from debian.org ***

# This script authored by Richard Guy 2015-03-10 based on a list of steps from Julian.


# setuptools installation
rm -f setuptools-13.0.2.zip
wget -nc --no-check-certificate  https://pypi.python.org/packages/source/s/setuptools/setuptools-13.0.2.zip
unzip -o setuptools-13.0.2
(cd setuptools-13.0.2; python2.7 setup.py install)

# ntplib installation
rm -f ntplib-0.3.2.tar.gz
wget -nc --no-check-certificate https://pypi.python.org/packages/source/n/ntplib/ntplib-0.3.2.tar.gz#md5=0f386dc00c0056ac4d77af0b4c21bb8e
gunzip -f ntplib-0.3.2.tar.gz 
tar xvf ntplib-0.3.2.tar
(cd ntplib-0.3.2; python2.7 setup.py install)

easy_install poster
easy_install pyyaml
easy_install numpy

# install libusb
rm -f libusb-1.0.9.tar.bz2
wget -nc http://sourceforge.net/projects/libusb/files/libusb-1.0/libusb-1.0.9/libusb-1.0.9.tar.bz2
bzip2 -d libusb-1.0.9.tar.bz2 
tar xvf libusb-1.0.9.tar
(cd libusb-1.0.9; ./configure; make; make install)
   
# Phidgets installation 
rm -f libphidget_2.1.8.20150227.tar.gz
wget -nc http://www.phidgets.com/downloads/libraries/libphidget.tar.gz
tar -zxvf libphidget_2.1.8.20150227.tar.gz
(cd libphidget-2.1.8.20150227; ./configure; make; make install)

# Phidgets Python installation
rm -f PhidgetsPython_2.1.8.20150109.zip
wget -nc http://www.phidgets.com/downloads/libraries/PhidgetsPython.zip
unzip -o PhidgetsPython_2.1.8.20150109.zip
(cd PhidgetsPython; python2.7 setup.py install)

# CSN client Python installation
mkdir -f PyCSN
(cd PyCSN; rm -f PyCSN.zip; wget -nc http://pcbunn.cacr.caltech.edu/PyCSN.zip; unzip -o PyCSN.zip)

# Now the client is ready to run. First we stop Leif's client and disable it,
# then we migrate Leif's client settings to the new
# client's format. This is all done by the MigrateClient.py process:

(cd PyCSN; python2.7 MigrateClient.py)
#Visually check the displayed yaml file created for errors (CSN_client.yaml)

#Run the new client    *** NEED an init.d/csnd-python start/stop script for this...
#  python2.7 PyCSN.py

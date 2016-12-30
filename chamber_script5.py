#!/usr/bin/python
import RPi.GPIO as GPIO
import time
import Adafruit_DHT
import sys
import requests

#---------
#Variables
#---------
#Database IP
dbIP = "192.168.1.220"
#Database port
dbPort = "8086"
#Influxdb database name
dbName = "test"
#Name of the curing chamber. Mostly useful if you have more than one.
chamberName = "meatsack"
#Desired temp/humidity set here.
desiredTemperature = 20.5
desiredHumidity = 80
#Set the drift or fluctuation allowed before outputs are changed to adjust the temp/humidity.
driftTemperature = 2
driftHumidity = 2


#Set timestamp in seconds. Only change if you need time accuracy beyond seconds.
seconds = int(time.time())

#Set GPIO pin specification. DO NOT CHANGE!
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

#----------------------------
#Setup temp/humidity sensors.
#----------------------------
#Supported sensors. DO NOT CHANGE!
DHT11  = 11
DHT22  = 22
AM2302 = 22

#Setup variable for a sensor list. DO NOT CHANGE!
allSensors = [[]]

#Installed sensors. This will vary depending on your setup. Only one internal
#temp/humidity sensor is required. Uncomment/change the values for up to 4 sensors.
#Sensor 1
#--------
sensor1Internal = AM2302
sensor1InternalPin = 27
allSensors[0] = [sensor1Internal, sensor1InternalPin, "internal", "sensor1"]
#Sensor 2
#--------
sensor2Internal = DHT22
sensor2InternalPin = 22
allSensors.insert(1, [sensor2Internal, sensor2InternalPin, "internal", "sensor2"])
#Sensor 3
#--------
sensor1External = AM2302
sensor1ExternalPin = 27
allSensors.insert(2, [sensor1External, sensor1ExternalPin, "external", "sensor1"])
#Sensor 4
#--------
sensor2External = AM2302
sensor2ExternalPin = 27
allSensors.insert(3, [sensor2External, sensor2ExternalPin, "external", "sensor2"])

#----------------------------------------
#Setup A/C relays and get current states.
#----------------------------------------
#Refrigerator
fridgeRelayPin = 17
#Humidifier
humidifierRelayPin = 0
#Dehumidifier
dehumidifierRelayPin = 0
#Heater
heaterRelayPin = 0

#Create Influxdb database. (This will probably be done when the Influxdb container is initialized, but for now....)
url = 'http://%s:%s/query' % (dbIP, dbPort)
headers = {'Content-Type': 'application/x-www-form-urlencoded'}
payload = "q=CREATE DATABASE %s\n" % dbName
r = requests.post(url, data=payload, headers=headers)

#Create class for watching relay states.
class Relay:
  def __init__(self, pin):
    self.pin = pin
    GPIO.setup(self.pin,GPIO.OUT)

  def setState(self, state):
    self.relayState = state
    self.stateChange = 0

  def updateState(self, newState):
    if self.relayState != newState:
      self.stateChange = 1
      self.relayState = newState
    else:
      self.relayState = newState

#Create fridge object from Relayclass and get it's initial state.
fridge = Relay(fridgeRelayPin)
fridge.setState(GPIO.input(fridge.pin))

#Function for getting temp/humidity readings.
def sensorReading():
  print "Reading %s, %s (ID %d)" % (allSensors[sensorIndex][3], allSensors[sensorIndex][2], sensorIndex)
  global temperature, humidity
  humidity, temperature = Adafruit_DHT.read_retry(allSensors[sensorIndex][0], allSensors[sensorIndex][1])
  #Ensure you get a reading from the sensor before continuing.
  if humidity is not None and temperature is not None:
    #Do any relays need to be adjusted?
    if sensorIndex is 0:
      relayAdjustments()
    #Output to Influxdb.
    influxSensorOutput()
  else:
    print('Failed to get reading. Try again!')


#Function to output temperature and humidity readings to Influxdb.
def influxSensorOutput():
  url = 'http://%s:%s/write?db=%s&precision=s' % (dbIP, dbPort, dbName)
  headers = {'Content-Type': 'application/x-www-form-urlencoded'}
  temperaturePayload = "temperature,chamber=%s,sensor=%s,location=%s value=%.1f %d\n" % (chamberName, allSensors[sensorIndex][3], allSensors[sensorIndex][2], temperature, seconds)
  print('Temp={0:0.1f}*C  Humidity={1:0.1f}%\n'.format(temperature, humidity))
  r = requests.post(url, data=temperaturePayload, headers=headers)
  #print temperaturePayload
  humidityPayload = "humidity,chamber=%s,sensor=%s,location=%s value=%.1f %d\n" % (chamberName, allSensors[sensorIndex][3], allSensors[sensorIndex][2], humidity, seconds)
  r = requests.post(url, data=humidityPayload, headers=headers)
  #print humidityPayload

#Output relay states to Influxdb.
def influxRelayOutput():
  url = 'http://%s:%s/write?db=%s&precision=s' % (dbIP, dbPort, dbName)
  headers = {'Content-Type': 'application/x-www-form-urlencoded'}
  fridgeRelayStatePayload = "fridgeRelayState,chamber=%s,stateChange=%d value=%d %d\n" % (chamberName, fridge.stateChange, fridge.relayState, seconds)
  r = requests.post(url, data=fridgeRelayStatePayload, headers=headers)
  #print(fridgeRelayStatePayload)
  #Heater
  #Humidifier
  #Dehumidifier


#Function to set relays based on sensor readings.
def relayAdjustments():
  #Temperature (Fridge and heater).
  print "Fridge relay = %d" % fridge.relayState
  print "Current temp = %.1f \nDesired temp = %.1f" %(temperature, desiredTemperature)
  print "Temp range", (desiredTemperature + driftTemperature), "-", (desiredTemperature - driftTemperature)
  if temperature > (desiredTemperature + driftTemperature):
    fridge.updateState(1)
    GPIO.output(fridge.pin,fridge.relayState)
    print(fridge.relayState)
    print "Temperature too high. Turning on refrigerator."
    print "Fridge state change is %d" % fridge.stateChange
  elif temperature < (desiredTemperature - driftTemperature):
    fridge.updateState(0)
    GPIO.output(fridge.pin,fridge.relayState)
    print(fridge.relayState)
    print "Temperature too low. Turning off refrigerator."
    print "Fridge state change is %d" % fridge.stateChange
  else:
    #turn off heater and fridge.
    print "Temperature is within range!"
  influxRelayOutput()

#Loop through all sensors and get a reading.
for sensorIndex, val in enumerate(allSensors):
  sensorReading()

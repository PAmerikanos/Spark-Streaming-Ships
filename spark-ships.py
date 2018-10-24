#!/usr/bin/env python
# -*- coding: utf-8 -*-

# usage:
# spark-submit --packages org.apache.spark:spark-streaming-kafka_2.11:1.6.3 spark-ships.py

import itertools

import numpy as np
import scipy.spatial as spatial

from datetime import datetime
from operator import itemgetter

from pyspark import SparkContext
from pyspark.streaming import StreamingContext
from pyspark.streaming.kafka import KafkaUtils
from pyspark.resultiterable import ResultIterable

from kafka import KafkaProducer

from math import degrees, radians, sin, cos, sqrt, asin, atan2

# kafka params
KAFKA_INPUT_TOPIC = 'spark-input'
KAFKA_OUTPUT_TOPIC = 'spark-output'

# spark streaming params
RDD_LENGTH = 1
RDD_WINDOW = 12
RDD_INTERVAL = 4
TIMEOUT = 0

# radius params
LOOK_AHEAD = 10
RADIUS_MIN = 100
RADIUS_PAD = 20
RADIUS_FACTOR = 20

# ship parse indices
_SOURCEMMSI = 0
_SPEEDOVERGROUND = 1
_LON = 2
_LAT = 3
_T = 4
_CALLSIGN = 5
_LENGTH = 6
_ALERT_RADIUS = 7
_WARN_RADIUS = 8

# grid partitioning
grid = []
bbox = [-10.0, 45.0, 0.0, 51.0]
step = 1.0

for lon in np.arange(bbox[0], bbox[2], step):
    for lat in np.arange(bbox[1], bbox[3], step):
        grid.append([lon, lat, lon + step, lat + step])

# locate cell ship belongs to
def grid_locate(lon, lat, r):
    for i, cell in enumerate(grid):
        if lon >= cell[0] and lon <= cell[2] and lat >= cell[1] and lat <= cell[3]:
            return i
    return None

# calculate distance between two points
# from https://rosettacode.org/wiki/Haversine_formula#Python
def haversine(lat1, lon1, lat2, lon2):
    R = 6372.8 # Earth radius in kilometers

    dLat = radians(lat2 - lat1)
    dLon = radians(lon2 - lon1)
    lat1 = radians(lat1)
    lat2 = radians(lat2)

    a = sin(dLat/2)**2 + cos(lat1)*cos(lat2)*sin(dLon/2)**2
    c = 2*asin(sqrt(a))

    return R * c

# calculate the middle point between two points
# adjusted from https://stackoverflow.com/questions/5895832/python-lat-long-midpoint-calculation-gives-wrong-result-when-longitude-90
def midpoint(lat1, lon1, lat2, lon2):
    dLon = radians(lon2 - lon1)
    lat1 = radians(lat1)
    lon1 = radians(lon1)
    lat2 = radians(lat2)

    dx = cos(lat2) * cos(dLon)
    dy = cos(lat2) * sin(dLon)

    lat3 = atan2(sin(lat1) + sin(lat2), sqrt((cos(lat1) + dx) * (cos(lat1) + dx) + dy * dy))
    lon3 = lon1 + atan2(dy, cos(lat1) + dx)

    lon3 = degrees(lon3)
    if lon3 < 180:
        lon3 += 360
    if lon3 > 180:
        lon3 -= 360

    return (degrees(lat3), lon3)

# load port and harbour coordinates
def load_ports(sc, path, i=0, j=1):
    print('Loading ports from ' + path + '...')

    ports = sc.textFile(path) \
        .map(lambda x: x.split(',')) \
        .filter(lambda x: x != None and len(x) > 1) \
        .map(lambda data: [float(data[i]), float(data[j])])

    return spatial.cKDTree(ports.collect())

# parses rdd
def parse_rdd(rdd):
    if not rdd.isEmpty():
        return rdd \
            .map(lambda x: x[1].split(',')) \
            .map(lambda data: [ \
                int(data[_SOURCEMMSI]), \
                float(data[_SPEEDOVERGROUND]), \
                float(data[_LON]), \
                float(data[_LAT]), \
                int(data[_T]), \
                str(data[_CALLSIGN]), \
                float(data[_LENGTH]) \
            ]) \
            .map(process_ship)

# calculates warning/alert radius for each tuple
def process_ship(ship):
    speed = ship[_SPEEDOVERGROUND]
    length = ship[_LENGTH]
    radius = [0.0, 0.0]

    try:
        radius[0] = length * 2
    except:
        # if length = nan
        radius[0] = RADIUS_MIN

    # radius in meters after LOOK_AHEAD seconds
    radius[1] = speed * 0.5144444 * LOOK_AHEAD
    if radius[1] < (radius[0] + RADIUS_PAD):
        radius[1] = radius[0] + RADIUS_PAD

    radius = map(lambda r: r * RADIUS_FACTOR, radius)

    ship.extend(radius)
    cell = grid_locate(ship[_LON], ship[_LAT], radius[1])
    return (cell, ship)

# filter tuples, keep only latest timestamp
def keep_latest(values):
    results = []

    for i in set(map(lambda x: x[_SOURCEMMSI], values)):
        results.append(sorted(filter(lambda x: x[_SOURCEMMSI] == i, values), key=itemgetter(_T), reverse=True)[0])

    return ResultIterable(results)

# filter tuples, keep those who are note in ports/harbours
def filter_ports(values):
    results = []

    results = filter(lambda x: not spatial.cKDTree.query_ball_point(harbours, (x[_LON], x[_LAT]), r=0.05, p=2.0, eps=0), values)

    return ResultIterable(results)

# calculate distance and output alert
def generate_alerts(values):
    results = []

    for (x, y) in itertools.combinations(values, 2):
        if x[_SOURCEMMSI] == y[_SOURCEMMSI]:
            continue

        dist = haversine(x[_LAT], x[_LON], y[_LAT], y[_LON]) * 1000
        alert_dist = x[_ALERT_RADIUS] + y[_ALERT_RADIUS]
        warn_dist = x[_WARN_RADIUS] + y[_WARN_RADIUS]

        #z = midpoint(x[_LAT], x[_LON], y[_LAT], y[_LON])
        #t = max(x[_T], y[_T])

        if dist < alert_dist:
            if (x[_T] > y[_T]):
                results.append([x[_SOURCEMMSI], x[_CALLSIGN], y[_SOURCEMMSI], y[_CALLSIGN], x[_LON], x[_LAT], datetime.fromtimestamp(x[_T]).strftime('%Y-%m-%d %H:%M:%S'), dist, 'ALERT'])
            else:
                results.append([y[_SOURCEMMSI], y[_CALLSIGN], x[_SOURCEMMSI], x[_CALLSIGN], y[_LON], y[_LAT], datetime.fromtimestamp(y[_T]).strftime('%Y-%m-%d %H:%M:%S'), dist, 'ALERT'])
        elif  dist < warn_dist:
            if (x[_T] > y[_T]):
                results.append([x[_SOURCEMMSI], x[_CALLSIGN], y[_SOURCEMMSI], y[_CALLSIGN], x[_LON], x[_LAT], datetime.fromtimestamp(x[_T]).strftime('%Y-%m-%d %H:%M:%S'), dist, 'WARN'])
            else:
                results.append([y[_SOURCEMMSI], y[_CALLSIGN], x[_SOURCEMMSI], x[_CALLSIGN], y[_LON], y[_LAT], datetime.fromtimestamp(y[_T]).strftime('%Y-%m-%d %H:%M:%S'), dist, 'WARN'])

    return ResultIterable(results)

print('Initializing SparkContext...')
sc = SparkContext(appName='SHIPS ALERTS')

print('Initializing StreamingContext...')
ssc = StreamingContext(sc, RDD_LENGTH)

# data from https://github.com/nvkelso/high-seas/tree/master/geo-data
#load_ports(sc, 'ports.csv', 3, 4)
harbours = load_ports(sc, 'ports_canal.csv')

print('Setting up output stream...')
producer = KafkaProducer()

def to_csv(v):
    if isinstance(v, ResultIterable):
        map(to_csv, v)
    else:
        msg = ','.join(str(d) for d in v)
        producer.send(KAFKA_OUTPUT_TOPIC, msg)
        producer.flush()

def rdd_to_csv(rdd):
    if rdd.isEmpty():
        return

    values = rdd.collect()
    for v in values:
        v = v[1]
        to_csv(v)
        #producer.send(KAFKA_OUTPUT_TOPIC, str(v))
        #producer.flush()

"""
    values = rdd.collect()
    for v in values:
        v = v[1]
        msg = ','.join(str(d) for d in v)
        producer.send(KAFKA_OUTPUT_TOPIC, str(v))
        producer.flush()
"""

print('Setting up input stream...')
ds = KafkaUtils.createDirectStream(ssc, [KAFKA_INPUT_TOPIC], {'metadata.broker.list': 'localhost:9092'}, fromOffsets=None)
ds = ds.transform(parse_rdd)

#ds.foreachRDD(rdd_to_csv)
#ds.pprint()

rs = ds.window(RDD_WINDOW, RDD_INTERVAL) \
    .groupByKey() \
    .mapValues(keep_latest) \
    .mapValues(filter_ports) \
    .mapValues(generate_alerts)
    #.transform(lambda x: x.map(lambda y: list(y[1])))

rs.foreachRDD(rdd_to_csv)
rs.pprint()

print('Streaming started...')
ssc.start()

stopped = False
if TIMEOUT > 0:
    stopped = ssc.awaitTerminationOrTimeout(TIMEOUT)
else:
    ssc.awaitTermination()

if not stopped :
    print('Stopping streaming context after timeout...')
    ssc.stop(True)
    print('Streaming context stopped.')

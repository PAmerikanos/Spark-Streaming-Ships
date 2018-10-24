#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import datetime
import signal
import sys
import time

import numpy as np
import pandas as pd

from kafka import KafkaProducer
from threading import Timer

class GracefulExit:
    now = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGTERM, self.exit)

    def exit(self, signum, frame):
        self.now = True

producer = KafkaProducer()
exit = GracefulExit()

#def ts2date(ts):
#    return datetime.datetime.fromtimestamp(float(ts))

def send_via_timer(*args):
    msg = ','.join(args[1:])
    if params.verbose:
        print msg
    if not params.dry_run:
        producer.send(params.topic, msg)

def send_directly(msg):
    if params.verbose:
        print msg
    if not params.dry_run:
        producer.send(params.topic, msg)

# helper functions to check valid input
def check_int(val):
    i = int(val)
    return check_positive(i)

def check_float(val):
    f = float(val)
    return check_positive(f)

def check_positive(val):
    if val < 0:
        raise argparse.ArgumentTypeError("'%s' is an invalid positive value" % val)
    return val

# parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument('-s', '--static', default='input/nari_static.csv')
parser.add_argument('-d', '--dynamic', default='input/nari_dynamic_1hour.csv')
parser.add_argument('-m', '--mode', default=1, type=check_float)
parser.add_argument('-t', '--topic', default='spark-input')
parser.add_argument('-c', '--csv', action='store_true')
parser.add_argument('-n', '--dry-run', action='store_true')
parser.add_argument('-v', '--verbose', action='store_true')
params = parser.parse_args()

# load csv files
try:
    static = pd.read_csv(
        params.static,
        usecols=['sourcemmsi', 'callsign', 'tobow', 'tostern'],
        converters={'callsign': str.strip},
        na_values={'sourcemmsi': ["1234500", "999999999"], 'callsign': '', 'tobow': 0, 'tostern': 0},
        skipinitialspace=True
    )
    dynamic = pd.read_csv(
        params.dynamic,
        usecols=['sourcemmsi', 'speedoverground', 'lon', 'lat', 't'],
        #parse_dates=['t'],
        #date_parser=ts2date,
        skipinitialspace=True
    )
except IOError as e:
    raise SystemExit("Error: %s" % e)

bbox = [-10.0, 45.0, 0.0, 51.0]
left = dynamic[
    (dynamic['lon'] >= bbox[0]) &
    (dynamic['lat'] >= bbox[1]) &
    (dynamic['lon'] <= bbox[2]) &
    (dynamic['lat'] <= bbox[3]) &
    (dynamic['speedoverground'] >= 0.0) &
    (dynamic['speedoverground'] <= 105.0)
].dropna()
right = static.drop_duplicates(subset='sourcemmsi', keep='first').dropna()

join = pd.merge(left, right, how='inner', on='sourcemmsi', validate='m:1').sort_values(['t', 'sourcemmsi'])

t_start = join['t'][0]
t_now = time.time()

timers = []

if params.csv:
    print ','.join(['sourcemmsi', 'speedoverground', 'lon', 'lat', 'timestamp', 'callsign', 'length'])

for i, row in join.iterrows():
    args = [
        str(row['sourcemmsi']),
        str(row['speedoverground']),
        str(row['lon']),
        str(row['lat']),
        str(row['t']),
        str(row['callsign']),
        str(row['tobow'] + row['tostern'])
    ]

    if params.mode > 0:
        t_delta = int(round(row['t'] - t_start - time.time() + t_now) / params.mode)
        args.insert(0, t_delta)

        timers.append(Timer(t_delta, send_via_timer, args))
	timers[-1].start()
    else:
        send_directly(','.join(args))

    if exit.now:
        for t in timers:
            t.cancel()
        break

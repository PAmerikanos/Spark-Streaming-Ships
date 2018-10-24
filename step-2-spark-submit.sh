#!/bin/bash

DIR_OUT="output"

LOG_OUT="$DIR_OUT/spark-log.txt"

spark-submit --packages org.apache.spark:spark-streaming-kafka_2.11:1.6.3 spark-ships.py 2>&1 | tee "$LOG_OUT"

#!/bin/bash

DIR_OUT="output"
CSV_OUT="$DIR_OUT/live.csv"

kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic spark-output 2>/dev/null | tee "$CSV_OUT"

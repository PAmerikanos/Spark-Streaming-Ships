#!/bin/bash

DIR_IN="input"
CSV_IN="$DIR_IN/nari_dynamic_1week.csv"

./kafka-stream.py -m4 -d "$CSV_IN" -vc

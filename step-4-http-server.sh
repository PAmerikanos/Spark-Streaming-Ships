#!/bin/bash

DIR_OUT="output"

CSV_IN="$DIR_OUT/live.csv"
CSV_OUT="$DIR_OUT/alerts.csv"

SLEEP=10
LOCKFILE=".update.lock"

HTTP_PORT=443
HTTP_ADDR="0.0.0.0"

quit()
{
   rm -f $LOCKFILE
}

trap 'quit' QUIT
trap 'quit' INT
trap 'quit' HUP

touch $LOCKFILE

#alert 's/ALERT$/#df0101/'
#alert 's/WARN$/#ffdf00/'

sudo http-server "$DIR_OUT" -p "$HTTP_PORT" -a "$HTTP_ADDR" -c -1 --gzip --no-dotfiles &

while true; do
echo "sourcemmsi_a,callsign_a,sourcemmsi_b,callsign_b,lon,lat,timestamp,distance,type" > "$CSV_OUT"
    sort -ut',' -k7 "$CSV_IN" >> "$CSV_OUT"

    if [ ! -f "$LOCKFILE" ]; then
        break
    fi

    sleep $SLEEP
done

# -*- coding: utf-8 -*-
#AUX SCRIPT - input databases, output DStream
# Usage:
# python shipStream.py
# spark-submit shipCount.py stream/

import time
import csv
#from pympler import tracker

#sourcemmsi,speedoverground,lon,lat,t,callsign,length
def joinF(sourcemmsi):
    with open("input/nari_static.csv", "rb") as joinFile:
        joiner = csv.reader(joinFile)
        found = False
        for row in joiner:
            if sourcemmsi == row[0]:
                found = True
                return [row[2].replace(" ", ""), int(row[5]) + int(row[6])]
                break
        if found == False:
            print ("ValueError - NaN static data found")
            with open("output/ERR_NaN_Static.txt", "a") as outfilet:
                outfilet.write(sourcemmsi + "\n")
            return ["NaN", 50.0]

#tr = tracker.SummaryTracker()
speed = int(input('Enter streaming speed (1:RealTime/10:Fast/0:Instant): '))
with open("input/nari_dynamic_1week.csv", "r") as infile:
    reader = csv.reader(infile)
    header = next(reader, None)
    firstLine = next(reader, None)
    lineList = []
    firstLine2 = [firstLine[0],firstLine[3],firstLine[6],firstLine[7],firstLine[8]]
    firstLine2.extend(joinF(firstLine[0]))
    lineList.append(firstLine2)
    baseTime = int(firstLine[8])
    for line in reader:
        if (int(line[0]) >= 0 and int(line[0]) <= 999999999) \
        and (float(line[3]) >= 0.0 and float(line[3]) <= 105.0) \
        and (float(line[6]) >= -11.0 and float(line[6]) <= 1.0) \
        and (float(line[7]) >= 44.0 and float(line[7]) <= 52.0) \
        and (int(line[8]) >= 1443650400 and int(line[8]) <= 1464739200):
            lastTime = int(lineList[len(lineList)-1][4])
            print ("Current: " + str(line[8]) + "s:")
            #print ("Last " + str(lastTime) + " seconds")​
            if int(line[8]) == lastTime:
                line2 = [line[0],line[3],line[6],line[7],line[8]]
                line2.extend(joinF(line[0]))
                lineList.append(line2)
                print (" Append")
            else:
                waitTime = int(line[8]) - lastTime
                if speed != 0:
                    time.sleep(float(waitTime/speed))
                filename = "stream/" + str(lineList[len(lineList)-1][4]) + ".csv"
                print (" Write previous after " + str(waitTime) + "s")
                with open(filename, "w") as outfile:
                    writer = csv.writer(outfile)
                    writer.writerows(lineList)
                lineList = []
                line2 = [line[0],line[3],line[6],line[7],line[8]]
                line2.extend(joinF(line[0]))
                lineList.append(line2)
                print (" Open New and Append")
        else:
            print ("ValueError - NaN data found")
            with open("output/ERR_NaN_Stream.txt", "a") as outfilee:
                outfilee.write(line + "\n")
#        tr.print_diff()

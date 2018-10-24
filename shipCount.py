# -*- coding: utf-8 -*-
# TEST SCRIPT - input DStream, output ship attribute count
# Usage:
# python shipStream.py
# spark-submit shipCount.py stream/ f


# Import libraries
from __future__ import print_function
import sys, shutil, os, glob, fiona, csv
import numpy as np
from math import radians, sin, cos, sqrt, asin
from pyspark import SparkContext
from pyspark.streaming import StreamingContext
import scipy.spatial as spatial

# Initialize variables
maxOut = False
RDD_length = 1
RDD_window = 200
RDD_interval = 2
grid = []
latS = 45.0
latN = 51.0
lonW = -10.0
lonE = 0.0
div = 1
step = float(1/div)

# Generate MBR - Grid Partitioning
for lat in np.arange(latS, latN, step):
    for lon in np.arange(lonW, lonE, step):
        grid.append([lon, lat, lon + step, lat + step])

# Generate list of ports
portShp = fiona.open("input/Fishing_Ports.shp")
portArray = []
for portCoo in portShp:
    portLon = portCoo['geometry']['coordinates'][0]
    portLat = portCoo['geometry']['coordinates'][1]
    if lonW<=portLon<=lonE and latS<=portLat<=latN:
        portArray.append(portCoo['geometry']['coordinates'])
portTree = spatial.cKDTree(portArray)

# Clear system folders to run spark process
def clearFolders():
#    shutil.rmtree('checkpoint/')
#    files = glob.glob('checkpoint/*.*')
#    for f in files:
#        os.remove(f)
    emptyFile = ["output/RED_Alert.csv","output/YEL_Alert.csv","output/ERR_NaN_Static.txt","output/ERR_NaN_Stream.txt","output/ShipsInPort.csv"]
    for file in emptyFile:
        f = open(file, "w")
        f.truncate()
        f.close()

# Calculate distance between coordinates (in meters)
# https://rosettacode.org/wiki/Haversine_formula#Python
def haversine(lat1, lng1, lat2, lng2):
    R = 6372.8 # Earth radius in kilometers
    dLat = radians(lat2 - lat1)
    dLon = radians(lng2 - lng1)
    lat1 = radians(lat1)
    lat2 = radians(lat2)
    a = sin(dLat/2)**2 + cos(lat1)*cos(lat2)*sin(dLon/2)**2
    c = 2*asin(sqrt(a))
    return R * c * 1000 # 

# Locate cell ship belongs to
def locate(ship):
    slon = float(ship[2])
    slat = float(ship[3])
    srad = float(ship[8])
    cellLocate = []
    for cell in grid:
        # Check center cell
        if  cell[0]<=slon<=cell[2] and cell[1]<=slat<=cell[3]:
            cellLocate.append(tuple(cell))
            # Check horizontal/vertical cells
            if haversine(slat,slon,slat,cell[0]) <= srad:
                    for adjCellW in grid:
                        if adjCellW[1] ==  cell[1] and adjCellW[2] == cell[0] and adjCellW[3] == cell[3]:
                            cellLocate.append(tuple(adjCellW))
            if haversine(slat,slon,cell[1],slon) <= srad:
                    for adjCellS in grid:
                        if adjCellS[0] ==  cell[0] and adjCellS[2] == cell[2] and adjCellS[3] == cell[1]:
                            cellLocate.append(tuple(adjCellS))
            if haversine(slat,slon,slat,cell[2]) <= srad:
                    for adjCellE in grid:
                        if adjCellE[0] ==  cell[2] and adjCellE[1] == cell[1] and adjCellE[3] == cell[3]:
                            cellLocate.append(tuple(adjCellE))
            if haversine(slat,slon,cell[3],slon) <= srad:
                    for adjCellN in grid:
                        if adjCellN[0] ==  cell[0] and adjCellN[1] == cell[3] and adjCellN[2] == cell[2]:
                            cellLocate.append(tuple(adjCellN))
            # Check diagonal cells
            if haversine(slat,slon,cell[3],cell[0]) <= srad:
                    for adjCellNW in grid:
                        if adjCellNW[1] ==  cell[3] and adjCellNW[2] == cell[0]:
                            cellLocate.append(tuple(adjCellNW))
            if haversine(slat,slon,cell[1],cell[0]) <= srad:
                    for adjCellSW in grid:
                        if adjCellSW[3] ==  cell[1] and adjCellSW[2] == cell[0]:
                            cellLocate.append(tuple(adjCellSW))
            if haversine(slat,slon,cell[1],cell[2]) <= srad:
                    for adjCellSE in grid:
                        if adjCellSE[3] ==  cell[1] and adjCellSE[0] == cell[2]:
                            cellLocate.append(tuple(adjCellSE))
            if haversine(slat,slon,cell[3],cell[2]) <= srad:
                    for adjCellNE in grid:
                        if adjCellNE[1] ==  cell[3] and adjCellNE[0] == cell[2]:
                            cellLocate.append(tuple(adjCellNE))
    return (cellLocate)

# Return cell/ship tuples
def mapTuples(line):
    shipObj = line.split(",")
    #IN: ID,speed,lon,lat,time,callsign,length - RadLen,RadSpd
    factor = 10 if maxOut else 1
    try:
        RadLen = float(shipObj[6])*2*factor
    except:
        RadLen = 100.0*factor              # Set min radius for Red Alert
    RadSpd = float(shipObj[1])/1.944*10*factor
    minRad = (RadLen + 100.0)*factor
    if RadSpd < minRad:
        RadSpd = minRad     # Set min radius for Yellow Alert
    shipObj.extend([RadLen,RadSpd])
    for cellObj in locate(shipObj):
        tupObj = (cellObj,shipObj)
        return (tuple(tupObj))

# Filter tuples not near ports
def filterPort(shipGroup):
    shipGList = list(shipGroup[1])
    for i in range(len(shipGList)):
        shipLon = float(shipGList[i][2])
        shipLat = float(shipGList[i][3])
        portNear = spatial.cKDTree.query_ball_point(portTree,(shipLon,shipLat), r=0.05, p=2., eps=0)
        if portNear:
            with open("output/ShipsInPort.csv", "a") as outfilep:
                    csv.writer(outfilep).writerow(shipGList[i])
            shipGList[i] = "DELETE"
#            if not maxOut:
#                del shipGList[i]    # Delete ship if neat port-tree node
#        for portCoo in portArray:
#            portLat = float(portCoo[1])
#            portLon = float(portCoo[0])
#            shipPortDist = haversine(shipLat, shipLon, portLat, portLon)
#            if shipPortDist <= 2000:
#                shipGList[i] = "DELETE"
    shipGList = [x for x in shipGList if x != "DELETE"]
    return (shipGroup[0], shipGList)

# Filter tuples with latest timestamp
def filterTime(shipGroup):
    shipGList = list(shipGroup[1])
    for i in range(len(shipGList)):
        for j in range(len(shipGList)):
            if j == i:
                continue
            if shipGList[i][0] == shipGList[j][0]:
                if float(shipGList[i][4]) >= float(shipGList[j][4]):
                    shipGList[j] = "DELETE" #del
                elif float(shipGList[i][4]) < float(shipGList[j][4]):
                    shipGList[i] = "DELETE" #del
    shipGList = [x for x in shipGList if x != "DELETE"]
    return (shipGroup[0], shipGList)

# Calculate distance and output alert
def compareAlert(shipFilter):
    shipList = list(shipFilter[1])
    for i in range(len(shipList)):
        for j in range(i + 1, len(shipList)):
            ship1 = shipList[i]
            ship2 = shipList[j]
            havDist = haversine(float(ship1[3]),float(ship1[2]),float(ship2[3]),float(ship2[2]))
            lenDist = ship1[7] + ship2[7]
            spdDist = ship1[8] + ship2[8]
            if havDist <= lenDist:
                with open("output/RED_Alert.csv", "a") as outfiler:
                    csv.writer(outfiler).writerow([ship1,ship2,havDist])
                return [ship1[0],ship2[0],"RED",str(havDist),str(lenDist),str(spdDist)]
            elif havDist <= spdDist and havDist > lenDist:
                with open("output/YEL_Alert.csv", "a") as outfiley:
                    csv.writer(outfiley).writerow([ship1,ship2,havDist])
                return [ship1[0],ship2[0],"YEL",str(havDist),str(lenDist),str(spdDist)]

# Open DStream and execute MapReduce
def functionToCreateContext():
    sc = SparkContext(appName="SparkStreamShipAlert")
    ssc = StreamingContext(sc, RDD_length)
    ssc.checkpoint("./checkpoint")
    lines = ssc.textFileStream(sys.argv[1])
    counts = lines.map(mapTuples).window(RDD_window, RDD_interval).groupByKey().map(filterPort).map(filterTime).map(compareAlert)
    counts.pprint()
    return ssc

# MAIN
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("ERROR: Usage: spark-submit shipCount.py stream/ (t/f)", file=sys.stderr)
        sys.exit(-1)
    if sys.argv[2] == "t": maxOut = True
    print("Maximizing Stream Output: " + str(maxOut))
    clearFolders()
    context = StreamingContext.getOrCreate("./checkpoint", functionToCreateContext)
    context.start()
    context.awaitTermination()

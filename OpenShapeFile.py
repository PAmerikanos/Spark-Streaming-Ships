import fiona
    
    
latS = 45.0
latN = 51.0
lonW = -10.0
lonE = 0.0
portShp = fiona.open("input/Fishing Ports.shp")
portArray = []
for portCoo in portShp:
    portLon = portCoo['geometry']['coordinates'][0]
    portLat = portCoo['geometry']['coordinates'][1]
    if lonW<=portLon<=lonE and latS<=portLat<=latN:
        portArray.append(portCoo['geometry']['coordinates'])
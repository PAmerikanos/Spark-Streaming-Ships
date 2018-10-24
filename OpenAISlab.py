import operator
import collections
from collections import OrderedDict

with open('C:\\Users\\student64\\Desktop\\[P1] AIS Data\\nari_dynamic.csv') as myfile:
    next(myfile)
    counts = dict()

    for line in myfile:
        words = line.split(",")

        key = words[0]
        if key in counts:
            counts[key] += 1
        else:
            counts[key] = 1

    count_sort = OrderedDict(sorted(counts.items(), key=lambda x: x[1]))

    sortedList = count_sort.items()
    print(sortedList)
    print(len(counts.keys())) 
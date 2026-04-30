from dataclasses import dataclass

import numpy as np

@dataclass
class Intersection:
    x: int
    y: int 
    num_cables: int 


def get_intersections(paths):
    res = {}
    for path in paths:
        for coord in path:
            coord = tuple(coord)
            res[coord] = res.get(coord, 0) + 1
    #print(res)
    intersections = []
    for coord in res:
        if res.get(coord) > 1:
            intersection = Intersection(coord[1], coord[0], res.get(coord)) #(The x and y are flipped in the tuple for whatever reason, no I will not be fixing it)
            intersections.append(intersection)
    #print(intersections)
    return intersections


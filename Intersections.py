from dataclasses import dataclass

import numpy as np
from collections import Counter

@dataclass
class Intersection:
    x: int
    y: int 
    num_cables: int 

def get_intersections(paths: list[np.array]):
    node_counts = Counter(node for path in paths for node in path)
    shared  = {node for node, count in node_counts.items() if count > 1}
    return shared 


import json
import argparse
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Tuple
import sys
import AStar as AStar
import Intersections as Intersections
import socket

@dataclass
class Room:
    width: float
    height: float


@dataclass
class Obstacle:
    shape: str          # "rect" | "circle" | "polygon" | "line"
    label: str = ""
    # rect
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    # circle
    cx: float = 0
    cy: float = 0
    radius: float = 0
    # polygon / line
    points: list = field(default_factory=list)
    thickness: float = 0.5


@dataclass
class Endpoint:
    id: str
    x: float
    y: float
    connects_to: Optional[str] = None
    cable_type: str = "generic"
    group: str = ""


@dataclass
class ParsedLayout:
    room: Room
    obstacles: list[Obstacle]
    penalty_zones: list[Obstacle]
    endpoints: list[Endpoint]
    resolution: float          # world units per grid cell
    grid: np.ndarray           # 2-D int array  (0=free, 1=wall/obstacle, 2=penalty zone)
    endpoint_coords: dict      # id → (row, col) in grid


def _parse_shape(raw: dict) -> Optional[Obstacle]:
    shape = raw.get("type", "rect")
    obs = Obstacle(shape=shape, label=raw.get("label", ""))

    if shape == "rect":
        obs.x      = float(raw["x"])
        obs.y      = float(raw["y"])
        obs.width  = float(raw["width"])
        obs.height = float(raw["height"])

    elif shape == "circle":
        obs.cx     = float(raw["cx"])
        obs.cy     = float(raw["cy"])
        obs.radius = float(raw["radius"])

    elif shape in ("polygon", "line"):
        obs.points = [[float(p[0]), float(p[1])] for p in raw["points"]]
        if shape == "line":
            obs.thickness = float(raw.get("thickness", 0.5))

    else:
        print(f"  [warn] Unknown shape type '{shape}' — skipped.")
        return None

    return obs


def parse_json(path: str) -> tuple[Room, list[Obstacle], list[Obstacle], list[Endpoint]]:
    with open("Rooms/"+path) as f:
        data = json.load(f)

    # --- Room ---
    r = data["room"]
    room = Room(width=float(r["width"]), height=float(r["height"]))

    # --- Obstacles ---
    obstacles = []
    for raw in data.get("obstacles", []):
        obs = _parse_shape(raw)
        if obs is not None:
            obstacles.append(obs)

    # --- Penalty zones ---
    penalty_zones = []
    for raw in data.get("penalty_zones", []):
        zone = _parse_shape(raw)
        if zone is not None:
            penalty_zones.append(zone)

    endpoints = []
    for raw in data.get("endpoints", []):
        ep = Endpoint(
            id          = str(raw["id"]),
            x           = float(raw["x"]),
            y           = float(raw["y"]),
            connects_to = raw.get("connects_to"),
            cable_type  = raw.get("cable_type", "generic"),
            group       = raw.get("group", ""),
        )
        endpoints.append(ep)

    return room, obstacles, penalty_zones, endpoints

def _world_to_cell(x: float, y: float, resolution: float) -> tuple[int, int]:
    """Convert world coordinates to (row, col) grid indices."""
    col = int(x / resolution)
    row = int(y / resolution)
    return row, col


def _rasterize_rect(grid: np.ndarray, obs: Obstacle, res: float, value: int = 1):
    rows, cols = grid.shape
    c0 = max(0, int(obs.x / res))
    c1 = min(cols, int((obs.x + obs.width) / res) + 1)
    r0 = max(0, int(obs.y / res))
    r1 = min(rows, int((obs.y + obs.height) / res) + 1)
    grid[r0:r1, c0:c1] = value


def _rasterize_circle(grid: np.ndarray, obs: Obstacle, res: float, value: int = 1):
    rows, cols = grid.shape
    r_cells = obs.radius / res
    cr = obs.cy / res
    cc = obs.cx / res

    r0 = max(0, int(cr - r_cells) - 1)
    r1 = min(rows, int(cr + r_cells) + 2)
    c0 = max(0, int(cc - r_cells) - 1)
    c1 = min(cols, int(cc + r_cells) + 2)

    for row in range(r0, r1):
        for col in range(c0, c1):
            # centre of cell in world coords
            cy_w = (row + 0.5) * res
            cx_w = (col + 0.5) * res
            if (cx_w - obs.cx) ** 2 + (cy_w - obs.cy) ** 2 <= obs.radius ** 2:
                grid[row, col] = value


def _rasterize_polygon(grid: np.ndarray, obs: Obstacle, res: float, value: int = 1):
    rows, cols = grid.shape
    pts = obs.points
    if len(pts) < 3:
        return

    xs = [p[0] / res for p in pts]
    ys = [p[1] / res for p in pts]
    min_r = max(0, int(min(ys)))
    max_r = min(rows - 1, int(max(ys)) + 1)

    for row in range(min_r, max_r + 1):
        # find x-intersections at this scanline
        x_ints = []
        n = len(pts)
        for i in range(n):
            x1, y1 = xs[i], ys[i]
            x2, y2 = xs[(i + 1) % n], ys[(i + 1) % n]
            if y1 == y2:
                continue
            if min(y1, y2) <= row < max(y1, y2):
                xi = x1 + (row - y1) * (x2 - x1) / (y2 - y1)
                x_ints.append(xi)
        x_ints.sort()
        for i in range(0, len(x_ints) - 1, 2):
            c0 = max(0, int(x_ints[i]))
            c1 = min(cols - 1, int(x_ints[i + 1]) + 1)
            grid[row, c0:c1] = value


def _rasterize_line(grid: np.ndarray, obs: Obstacle, res: float, value: int = 1):
    half = obs.thickness / 2
    pts = obs.points
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        # bounding box of segment
        rows, cols = grid.shape
        r0 = max(0, int((min(y1, y2) - half) / res))
        r1 = min(rows, int((max(y1, y2) + half) / res) + 2)
        c0 = max(0, int((min(x1, x2) - half) / res))
        c1 = min(cols, int((max(x1, x2) + half) / res) + 2)

        dx, dy = x2 - x1, y2 - y1
        seg_len_sq = dx * dx + dy * dy

        for row in range(r0, r1):
            for col in range(c0, c1):
                px = (col + 0.5) * res
                py = (row + 0.5) * res
                if seg_len_sq == 0:
                    dist = ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
                else:
                    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
                    dist = ((px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2) ** 0.5
                if dist <= half:
                    grid[row, col] = value

def build_grid(
    room: Room,
    obstacles: list[Obstacle],
    penalty_zones: list[Obstacle],
    endpoints: list[Endpoint],
    resolution: float = 1.0,
) -> ParsedLayout:

    grid_cols = int(np.ceil(room.width  / resolution))
    grid_rows = int(np.ceil(room.height / resolution))
    grid = np.zeros((grid_rows, grid_cols), dtype=np.int8)

    rasterizers = {
        "rect":    _rasterize_rect,
        "circle":  _rasterize_circle,
        "polygon": _rasterize_polygon,
        "line":    _rasterize_line,
    }

    # Rasterize penalty zones first (value 2) so that obstacles, rasterized
    # next with value 1, naturally overwrite any cells where the two overlap.
    for zone in penalty_zones:
        fn = rasterizers.get(zone.shape)
        if fn:
            fn(grid, zone, resolution, value=2)
        print(f"  [penalty]  {zone.shape:8s}  label='{zone.label}'")

    for obs in obstacles:
        fn = rasterizers.get(obs.shape)
        if fn:
            fn(grid, obs, resolution, value=1)
        print(f"  [obstacle] {obs.shape:8s}  label='{obs.label}'")

    # --- Map endpoints to grid cells ---
    endpoint_coords = {}
    for ep in endpoints:
        row, col = _world_to_cell(ep.x, ep.y, resolution)
        row = max(0, min(grid_rows - 1, row))
        col = max(0, min(grid_cols - 1, col))

        if grid[row, col] == 1:
            print(f"  [warn] Endpoint '{ep.id}' at ({ep.x},{ep.y}) lands inside an obstacle — nudging to nearest free cell.")
            found = False
            for d in range(1, max(grid_rows, grid_cols)):
                for dr in range(-d, d + 1):
                    for dc in range(-d, d + 1):
                        nr, nc = row + dr, col + dc
                        if 0 <= nr < grid_rows and 0 <= nc < grid_cols and grid[nr, nc] == 0:
                            row, col = nr, nc
                            found = True
                            break
                    if found:
                        break
                if found:
                    break

        endpoint_coords[ep.id] = (row, col)
        print(f"  [endpoint] id='{ep.id}'  world=({ep.x},{ep.y})  cell=({row},{col})  cable='{ep.cable_type}'")

    return ParsedLayout(
        room=room,
        obstacles=obstacles,
        penalty_zones=penalty_zones,
        endpoints=endpoints,
        resolution=resolution,
        grid=grid,
        endpoint_coords=endpoint_coords,
    )

def visualize_matplotlib(layout: ParsedLayout, nodes: int):
    paths = []
    plotted_intersections = []
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("  [info] matplotlib not installed — skipping graphical visualisation.")
        return

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_title("Cable Layout Grid", fontsize=14, fontweight="bold")

    # Draw grid
    display = np.zeros((*layout.grid.shape, 3))
    display[layout.grid == 0] = [0.97, 0.97, 0.97]   # free: light grey
    display[layout.grid == 1] = [0.18, 0.18, 0.22]   # obstacle: near-black
    display[layout.grid == 2] = [1.00, 0.85, 0.40]   # penalty zone: amber
    ax.imshow(display, origin="upper", interpolation="nearest")

    # Draw endpoints
    colors = plt.cm.tab10.colors
    plotted_endpoints = []
    for i, ep in enumerate(layout.endpoints):
        row, col = layout.endpoint_coords[ep.id]
        color = colors[i % len(colors)]
        plotted_endpoints.append((col, row))
        ax.plot(col, row, "o", color=color, markersize=10, zorder=5)
        ax.text(col + 0.5, row - 0.5, ep.id, fontsize=7, color=color, fontweight="bold")


    for i, ep in enumerate(layout.endpoints): # Locate start and endpoints indicated by user in JSON
        if ep.connects_to is not None:
            end = layout.endpoint_coords[ep.connects_to]
            start = layout.endpoint_coords[ep.id]
            path = AStar.find_path(layout.grid, start, end) # Use start and endpoints as input for pathfinding function
            if path:
                path = np.array(path)
                paths.append(path)
                plt.plot(path[:,1], path[:, 0]) # If a path exists, plot it
        else:
            continue

    intersections = Intersections.get_intersections(paths) # Locate intersections 
    sorted_intersections = sorted(intersections, key=lambda x: x.num_cables) # Prioritize intersections based on number of cables running through them
    num_intersections = len(sorted_intersections)
    if(nodes >= num_intersections): # If number of nodes is greater than number of intersections:
        for coord in sorted_intersections:
            if (coord.x.item(), coord.y.item()) not in plotted_endpoints: # Make sure that endpoint is not considered an intersection
                ax.plot(coord.x, coord.y, "o", color='gray', markersize=10, zorder=5)
    else: # Otherwise, use nodes on as many intersections as possible
        remaining_nodes = nodes
        index = 0
        while remaining_nodes > 0:
            coord = sorted_intersections[index]
            if (coord.x.item(), coord.y.item()) not in plotted_endpoints: # Make sure that endpoint is not considered an intersection
                ax.plot(coord.x, coord.y, "o", color='gray', markersize=10, zorder=5)
            index += 1
            remaining_nodes -=1

    rows, cols = layout.grid.shape
    ax.set_xlim(-0.5, cols - 0.5)
    ax.set_ylim(rows - 0.5, -0.5)
    ax.set_xlabel("Room Width")
    ax.set_ylabel("Room Height")

    patches = [
        mpatches.Patch(color=[0.97, 0.97, 0.97], label="Free space"),
        mpatches.Patch(color=[0.18, 0.18, 0.22], label="Obstacle"),
        mpatches.Patch(color=[1.00, 0.85, 0.40], label="Penalty zone"),
        mpatches.Patch(color="steelblue", label="Endpoint"),
    ]
    ax.legend(handles=patches, loc="upper right", fontsize=8)
    plt.tight_layout()
    plt.savefig("layout_preview.png", dpi=150)
    print("  [info] Saved graphical preview to layout_preview.png")
    plt.show()

ESP32_IP = '192.168.4.1' # This is the default IP 
PORT = 5005 

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.connect((ESP32_IP, PORT))
except TimeoutError:
    print("Device not connected to cable holder network, please restart.")

def check_devices() -> int:
    print("Reading Network...")
    data = sock.recv(1024).decode().strip()
    #num_nodes = data.parseInt()
    print(f'Received Data {data} Node(s) connected')
    return int(data)


def main():
    parser = argparse.ArgumentParser(description="Parse a JSON room layout into a numpy grid.")
    parser.add_argument("layout_file", help="Path to the JSON layout file")
    parser.add_argument("--resolution", type=float, default=1.0,
                        help="Grid cell size in world units (default: 1.0)")
    parser.add_argument("--visualize", action="store_true",
                        help="Show matplotlib visualisation (requires matplotlib)")
    parser.add_argument("--save-grid", metavar="PATH",
                        help="Save the numpy grid to a .npy file")
    args = parser.parse_args()

    print(f"\nParsing '{args.layout_file}'  (resolution={args.resolution})\n")

    room, obstacles, penalty_zones, endpoints = parse_json(args.layout_file)
    layout = build_grid(room, obstacles, penalty_zones, endpoints, resolution=args.resolution)
    
    
    while True:
        num_nodes = check_devices()
        visualize_matplotlib(layout, num_nodes)
        # visualize_matplotlib(layout, 2)

if __name__ == "__main__":
    main()
# Cable Holder

A two-part system for planning and physically organizing cable runs in a room. You sketch a room layout in a browser editor, the optimizer finds the shortest cable paths between endpoints, and a mesh of ESP32 "cable holder" nodes reports how many physical clips are available so the optimizer can place them at the most-crossed intersections.

## Repository layout

- [Optimizer/](Optimizer/) — Python tools that parse a room, run A* between endpoints, and visualize the result.
  - [main.py](Optimizer/main.py) — entry point. Connects to the ESP32 host, builds the grid, plots paths and node placements.
  - [editor.py](Optimizer/editor.py) — serves the browser-based room layout editor and writes the result to a JSON file.
  - [AStar.py](Optimizer/AStar.py) — A* implementation with a configurable penalty weight for "penalty zone" cells.
  - [Intersections.py](Optimizer/Intersections.py) — finds cells where multiple paths cross.
  - [room_layout_editor.html](Optimizer/room_layout_editor.html) — the editor UI (loaded by `editor.py`).
  - [Rooms/](Optimizer/Rooms/) — saved room layouts in JSON.
- [Onboard ESP32/cableholder/cableholder.ino](Onboard%20ESP32/cableholder/cableholder.ino) — firmware for the physical cable-holder nodes. The first ESP32 to boot becomes the WiFi host; the rest join as clients and report their presence.

## Requirements

- Python 3.10+
- `numpy` (required)
- `matplotlib` (required for visualization)
- A modern browser (for the layout editor)
- One or more ESP32 boards flashed with [cableholder.ino](Onboard%20ESP32/cableholder/cableholder.ino) (only needed for live node counts; see "Running without hardware" below)

```
pip install numpy matplotlib
```

## Workflow

### 1. Draw a room layout

From the `Optimizer/` directory:

```
python editor.py
```

This serves [room_layout_editor.html](Optimizer/room_layout_editor.html) on localhost, opens it in your browser, and waits for you to export. The exported JSON is written to `Rooms/layout.json` by default.

Custom output path or port:

```
python editor.py -o Rooms/felix_room.json
python editor.py --port 9000
```

In the editor you place:
- **Room dimensions** (width × height in world units)
- **Obstacles** — rectangles, circles, polygons, or thick lines that paths must avoid
- **Penalty zones** — areas paths can cross but will pay an extra cost (weight set by `PENALTY_WEIGHT` in [AStar.py:6](Optimizer/AStar.py#L6))
- **Endpoints** — labeled points with optional `connects_to` to define cable runs

You can also hand-edit any file in [Rooms/](Optimizer/Rooms/). See [Rooms/room.json](Optimizer/Rooms/room.json) for the schema.

### 2. Power on the ESP32 mesh

Flash [cableholder.ino](Onboard%20ESP32/cableholder/cableholder.ino) to each ESP32. On boot they negotiate automatically:

- The first board to come up becomes the **host** and creates the `CableHolder Network` WiFi AP (lights the HOST LED on GPIO 27).
- Every later board joins as a **client** and lights its connection LED on GPIO 26.
- The host tracks the live node count and broadcasts it on TCP port `5005`.

Connect your laptop to the `CableHolder Network` AP before running the optimizer.

### 3. Run the optimizer

From the `Optimizer/` directory:

```
python main.py layout.json
```

`main.py` will:
1. Parse the layout from `Rooms/layout.json`.
2. Rasterize the room into a grid (obstacles = blocked, penalty zones = expensive).
3. Connect to the ESP32 host at `192.168.4.1:5005` and read the current node count.
4. Run A* between every endpoint pair connected via `connects_to`.
5. Find path intersections, sort by traffic, and mark the top-N as node placements — where N is the live node count from the mesh.
6. Render the layout, paths, and node placements, saving a copy to `layout_preview.png`.

Flags:

| Flag | Meaning |
|---|---|
| `--resolution <float>` | Grid cell size in world units (default `1.0`). Smaller = finer paths, slower. |
| `--visualize` | Force-show the matplotlib window. |
| `--save-grid <path>` | Save the raw numpy grid to a `.npy` file. |

Example:

```
python main.py felix_room.json --resolution 0.5
```

### Running without hardware

[main.py:398-401](Optimizer/main.py#L398-L401) loops on `check_devices()` which reads from the ESP32. If you want to run the optimizer offline, swap that loop for a fixed node count:

```python
visualize_matplotlib(layout, 2)
```

## Layout JSON schema

```json
{
  "room": { "width": 20, "height": 15 },
  "obstacles": [
    { "type": "rect",    "x": 3,  "y": 2, "width": 4, "height": 3, "label": "server_rack" },
    { "type": "circle",  "cx": 10, "cy": 7, "radius": 1.5,         "label": "pillar" },
    { "type": "polygon", "points": [[1,1],[2,1],[2,3],[1,3]],      "label": "wall" },
    { "type": "line",    "points": [[5,5],[12,5]], "thickness": 0.4 }
  ],
  "penalty_zones": [
    { "type": "rect", "x": 0, "y": 6, "width": 20, "height": 2, "label": "walkway" }
  ],
  "endpoints": [
    { "id": "A1", "x": 0,  "y": 0,  "connects_to": "B1", "cable_type": "ethernet" },
    { "id": "B1", "x": 19, "y": 14 }
  ]
}
```

Endpoints without `connects_to` are treated as destinations only — define the relationship on the source side.

## How it fits together

```
   ┌──────────────┐    JSON     ┌──────────────┐
   │ Browser      │────────────▶│ editor.py    │
   │ editor.html  │             │ Rooms/*.json │
   └──────────────┘             └──────┬───────┘
                                       │
                                       ▼
                                ┌──────────────┐
                                │ main.py      │
                                │  parse + A*  │
                                └──────┬───────┘
                                       │  TCP :5005
                                       ▼
                                ┌──────────────┐
                                │ ESP32 host   │◀── clients ── ESP32 nodes
                                │ softAP       │              (cableholder.ino)
                                └──────────────┘
```

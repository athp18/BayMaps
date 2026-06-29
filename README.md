# Bay Area Pathfinder

A traffic-aware routing app for the San Francisco Bay Area. Routes are computed over an OSMnx road graph using a custom Dijkstra implementation, with travel times adjusted using real Caltrans PEMS sensor data and an XGBoost congestion model.

## How it works

**Data layer**

Historical speeds come from Caltrans PeMS District 4 5-minute station data. A preprocessing script snaps each sensor to the nearest road segment and aggregates speeds by hour-of-week (0-167), producing a parquet lookup table covering ~1,400 edges. At request time, the current hour's sensor readings override OSM default speeds for those edges.

**ML layer**

For edges without direct sensor coverage, an XGBoost model predicts a congestion multiplier (1.0 to 4.0). Each edge is represented by road type, OSM speed, length, node degree, and distance/congestion-ratio features from the 5 nearest PEMS sensors. Six models are trained, one per time bucket (weekday AM peak, midday, PM peak, night; weekend day, night). Best R2: 0.79 (weekend day), 0.66 (weekday PM peak).

**Routing**

Custom Dijkstra runs over the graph at request time. Priority: live PEMS speed (sensor-covered edges) over XGBoost multiplier (uncovered edges) over OSM default travel time.

**Frontend**

React + TypeScript + Leaflet. Click to set origin and destination, see the route drawn on the map with distance, duration, and a traffic-adjustment flag.

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, OSMnx, NetworkX, XGBoost, SciPy |
| Frontend | React 18, TypeScript, Vite, Leaflet |
| Data | Caltrans PeMS D4, OpenStreetMap |
| Infrastructure | Docker Compose |

## Project layout

```
backend/
  app/
    api/        # FastAPI routes
    core/       # Dijkstra, graph loading, PEMS speed lookup
    etl/        # Live traffic ETL loop
    models/     # XGBoost inference, route scorer
    schemas/    # Pydantic request/response models
  scripts/
    download_pems.py        # Fetch raw PeMS files
    build_speed_lookup.py   # Build speed_lookup.parquet
    build_training_data.py  # Build XGBoost training features
    train_xgb.py            # Train and save per-bucket models
  weights/                  # xgb_<bucket>.json (not committed)
  data/                     # bay_area.graphml, speed_lookup.parquet (not committed)
frontend/
  src/
    components/  # Map, SearchBar, RoutePanel
    hooks/       # useRoute, useTraffic
    services/    # API client
```

## Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for training scripts, run locally)
- A Caltrans PeMS account (free) to download station data

### 1. Build the road graph

```bash
cd backend
docker compose run --rm --no-deps backend python -m scripts.download_graph
```

This downloads the Bay Area OSMnx graph and saves it to `backend/data/bay_area.graphml`.

### 2. Download PeMS data

```bash
python -m scripts.download_pems
```

Downloads District 4 5-minute station files into `backend/data/`. You need at least a few weeks of data for stable speed estimates. The script requires your PeMS credentials in `.env`.

### 3. Build the speed lookup

```bash
docker compose run --rm --no-deps backend python -m scripts.build_speed_lookup
```

Produces `backend/data/pems/speed_lookup.parquet`.

### 4. Build training data and train XGBoost

```bash
# Build features (needs the graph, so run in Docker)
docker compose run --rm --no-deps backend python -m scripts.build_training_data

# Train models (run locally)
cd backend
python -m scripts.train_xgb
```

Saves six model files to `backend/weights/`.

### 5. Run the app

```bash
docker compose up --build
```

Frontend: `http://localhost:5173`
API: `http://localhost:8000/api/health`

## API

```
POST /api/route
{
  "origin_lat": 37.7749,
  "origin_lng": -122.4194,
  "dest_lat": 37.3382,
  "dest_lng": -121.8863
}

GET /api/health
GET /api/traffic
```

## Environment variables

Copy `.env.example` to `.env` and fill in:

```
PEMS_USERNAME=your_pems_email
PEMS_PASSWORD=your_pems_password
```

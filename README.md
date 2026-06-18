# Fuel Route API

A Django REST API that calculates optimal fuel stop routes across the USA, minimizing total fuel cost for a vehicle with a 500-mile range and 10 MPG fuel economy.

## Features

- Accepts any two US locations (city/state, address, landmark)
- Computes the full driving route via a **single API call** to OpenRouteService
- Detects which US states are traversed **completely offline** using a KDTree spatial index — no extra API calls
- Applies a **greedy optimization algorithm** to decide where to stop for fuel based on state-level prices
- Returns route geometry (GeoJSON), fuel stops with recommended stations, and total trip cost
- Parallel geocoding for fast response times

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django 6 + Django REST Framework |
| Routing | OpenRouteService (ORS) — 1 API call |
| Geocoding | Nominatim / OpenStreetMap — 2 API calls |
| State detection | scipy cKDTree (fully offline) |
| Fuel prices | CSV data — 8,151 US truck stop stations |
| Concurrency | ThreadPoolExecutor (parallel geocoding) |
| Performance | `lru_cache` for CSV loading and spatial index |

**Total external API calls per request: 3** (2 geocoding + 1 routing)

## Project Structure

```
fuel-route-api/
├── api/
│   ├── data/
│   │   └── fuel_prices.csv          # 8,151 US truck stop stations
│   ├── services/
│   │   ├── geocoding.py             # Nominatim geocoding
│   │   ├── routing.py               # OpenRouteService integration
│   │   ├── fuel_prices.py           # CSV loader + price aggregation
│   │   ├── state_locator.py         # Offline state detection via KDTree
│   │   └── optimizer.py             # Greedy fuel stop algorithm
│   ├── serializers.py
│   ├── views.py                     # RouteView + HealthView
│   └── urls.py
├── fuel_route/
│   ├── settings.py
│   └── urls.py
├── requirements.txt
├── manage.py
└── .env                             # API keys (not committed)
```

## How the Algorithm Works

1. **Geocode** start and end locations in parallel (Nominatim)
2. **Fetch route** from OpenRouteService — returns full polyline with thousands of coordinate points
3. **Compute cumulative distances** using the Haversine formula along each coordinate pair
4. **Detect state boundaries** offline using a KDTree built from ~400 embedded US city coordinates — no API calls
5. **Optimize fuel stops** with a greedy lookahead algorithm:
   - Start with a full tank (500 miles)
   - At each state boundary, look ahead within the remaining tank range
   - If the current state has the **cheapest price in range** → fill to full
   - If a **cheaper state is reachable** → buy only enough to get there
   - Always maintain a 20-mile safety buffer

## Setup

### Prerequisites

- Python 3.10+
- An [OpenRouteService API key](https://openrouteservice.org/) (free tier: 2,000 requests/day)

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd fuel-route-api

# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root:

```env
ORS_API_KEY=your_openrouteservice_api_key_here
SECRET_KEY=your-django-secret-key
DEBUG=True
```

### Run

```bash
python manage.py migrate
python manage.py runserver
```

The API will be available at `http://localhost:8000`.

## API Reference

### POST `/api/route/`

Calculate the optimal fuel route between two US locations.

**Request Body**

```json
{
  "start": "New York, NY",
  "end": "Los Angeles, CA"
}
```

| Field | Type | Description |
|---|---|---|
| `start` | string | Starting location within the USA |
| `end` | string | Destination within the USA |

**Response**

```json
{
  "route": {
    "start": "New York, NY",
    "end": "Los Angeles, CA",
    "start_coordinates": { "lat": 40.71427, "lon": -74.00597 },
    "end_coordinates": { "lat": 34.05223, "lon": -118.24368 },
    "total_distance_miles": 2793.61,
    "total_duration_hours": 44.9,
    "map_url": "https://www.openstreetmap.org/directions?...",
    "geometry": {
      "type": "LineString",
      "coordinates": [[-74.00597, 40.71427], ["..."]]
    }
  },
  "fuel_stops": [
    {
      "stop_number": 1,
      "state": "OH",
      "mile_marker": 462,
      "lat": 41.49932,
      "lon": -81.69436,
      "price_per_gallon": 2.999,
      "gallons_purchased": 0.7,
      "cost": 2.1,
      "recommended_station": {
        "name": "Pilot Travel Center",
        "address": "123 Highway Rd",
        "city": "Cleveland",
        "state": "OH",
        "price": 2.999
      }
    }
  ],
  "summary": {
    "total_distance_miles": 2793.61,
    "vehicle_range_miles": 500,
    "vehicle_mpg": 10,
    "total_gallons_needed": 279.36,
    "total_fuel_cost_usd": 745.57,
    "average_price_per_gallon": 3.025,
    "number_of_fuel_stops": 6,
    "states_traversed": ["NY", "PA", "OH", "IN", "IL", "IA", "NE", "CO", "UT", "NV", "CA"]
  }
}
```

### GET `/api/health/`

Check service status and verify the fuel price dataset is loaded.

**Response**

```json
{
  "status": "ok",
  "fuel_stations_loaded": 8151,
  "states_covered": 50
}
```

## Testing with Postman

### 1. Health Check
- Method: `GET`
- URL: `http://localhost:8000/api/health/`

### 2. Route Calculation
- Method: `POST`
- URL: `http://localhost:8000/api/route/`
- Headers: `Content-Type: application/json`
- Body (raw JSON):
```json
{
  "start": "New York, NY",
  "end": "Los Angeles, CA"
}
```

Other example routes to try:
```json
{ "start": "Miami, FL", "end": "Seattle, WA" }
{ "start": "Chicago, IL", "end": "Houston, TX" }
{ "start": "Boston, MA", "end": "Denver, CO" }
```

### 3. View the Route on a Map

The response includes a `map_url` field — open it in your browser to see the full route plotted on OpenStreetMap.

## Vehicle Specs

Configurable via `settings.py` or environment variables:

| Parameter | Default | Description |
|---|---|---|
| `VEHICLE_RANGE_MILES` | 500 | Max range on a full tank |
| `VEHICLE_MPG` | 10 | Fuel economy in miles per gallon |

## Fuel Price Data

The CSV dataset contains **8,151 truck stop stations** across all 50 US states. Prices are aggregated by state and the algorithm uses the minimum (cheapest) price per state as the decision metric. Each fuel stop response includes the specific recommended station with its name, address, and price.

## Error Responses

| Status | Description |
|---|---|
| `400 Bad Request` | Missing/invalid `start` or `end`, or location not found in USA |
| `502 Bad Gateway` | Routing API error (ORS unreachable or quota exceeded) |

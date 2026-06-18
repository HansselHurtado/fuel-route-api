import requests
from django.conf import settings


class RoutingService:
    """OpenRouteService (ORS) routing — 1 API call for the entire route."""

    BASE_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    KM_TO_MILES = 0.621371

    def get_route(
        self, start: tuple[float, float], end: tuple[float, float]
    ) -> dict:
        """
        Fetch driving route between two (lat, lon) pairs.
        Returns dict with 'distance_miles', 'duration_seconds', 'coordinates' list.
        Makes exactly ONE API call to ORS.
        """
        if not settings.ORS_API_KEY:
            raise ValueError(
                "ORS_API_KEY is not set. Get a free key at https://openrouteservice.org"
            )

        # ORS expects [lon, lat] order
        payload = {
            "coordinates": [
                [start[1], start[0]],
                [end[1], end[0]],
            ],
            "units": "km",
            "geometry_simplify": False,
            "instructions": False,
        }

        response = requests.post(
            self.BASE_URL,
            json=payload,
            headers={
                "Authorization": settings.ORS_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        feature = data["features"][0]
        summary = feature["properties"]["summary"]
        # GeoJSON coordinates are [lon, lat]
        coords_lonlat = feature["geometry"]["coordinates"]

        distance_miles = summary["distance"] * self.KM_TO_MILES
        duration_seconds = summary["duration"]

        # Convert to (lat, lon) tuples for internal use
        coords_latlon = [(c[1], c[0]) for c in coords_lonlat]

        return {
            "distance_miles": round(distance_miles, 2),
            "duration_seconds": round(duration_seconds),
            "duration_hours": round(duration_seconds / 3600, 2),
            "coordinates": coords_latlon,          # [(lat, lon), ...]
            "geojson_coordinates": coords_lonlat,   # [[lon, lat], ...] for output
        }

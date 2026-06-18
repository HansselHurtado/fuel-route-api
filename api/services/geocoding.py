import requests


class GeocodingService:
    """Nominatim (OpenStreetMap) geocoder — free, no API key required."""

    BASE_URL = "https://nominatim.openstreetmap.org/search"
    HEADERS = {"User-Agent": "FuelRouteAPI/1.0 (hanssel.hurtado@paymon.io)"}

    def geocode(self, location: str) -> tuple[float, float]:
        """Return (lat, lon) for a US location string. Raises ValueError if not found."""
        response = requests.get(
            self.BASE_URL,
            params={
                "q": location,
                "format": "json",
                "limit": 1,
                "countrycodes": "us",
                "addressdetails": 1,
            },
            headers=self.HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()
        if not results:
            raise ValueError(f"Location not found in the USA: '{location}'")
        r = results[0]
        return float(r["lat"]), float(r["lon"])

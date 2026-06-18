import math
from concurrent.futures import ThreadPoolExecutor, as_completed

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import RouteRequestSerializer
from .services.geocoding import GeocodingService
from .services.routing import RoutingService
from .services.fuel_prices import FuelPricesService
from .services.state_locator import build_route_segments
from .services.optimizer import find_optimal_fuel_stops


def _compute_cumulative_miles(coords: list[tuple]) -> list[float]:
    """Haversine cumulative distances along route coordinates."""
    R = 3958.8  # Earth radius in miles
    miles = [0.0]
    for i in range(1, len(coords)):
        lat1, lon1 = math.radians(coords[i - 1][0]), math.radians(coords[i - 1][1])
        lat2, lon2 = math.radians(coords[i][0]), math.radians(coords[i][1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        d = 2 * R * math.asin(math.sqrt(a))
        miles.append(miles[-1] + d)
    return miles


class RouteView(APIView):
    """
    POST /api/route/
    Body: {"start": "New York, NY", "end": "Los Angeles, CA"}

    Returns the optimal route with cost-effective fuel stops.
    API calls: 2 (Nominatim geocoding) + 1 (ORS routing) = 3 total.
    """

    geocoder = GeocodingService()
    router = RoutingService()
    fuel_svc = FuelPricesService()

    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        start_query = serializer.validated_data["start"]
        end_query = serializer.validated_data["end"]

        # --- Step 1: Geocode start and end in parallel (2 Nominatim calls) ---
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                fut_start = executor.submit(self.geocoder.geocode, start_query)
                fut_end = executor.submit(self.geocoder.geocode, end_query)
                start_coords = fut_start.result()
                end_coords = fut_end.result()
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # --- Step 2: Get route from ORS (1 routing API call) ---
        try:
            route = self.router.get_route(start_coords, end_coords)
        except Exception as e:
            return Response(
                {"error": f"Routing API error: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        coords = route["coordinates"]
        total_miles = route["distance_miles"]

        # --- Step 3: Compute cumulative distances along route ---
        cum_miles = _compute_cumulative_miles(coords)
        # Normalize to match ORS reported distance
        if cum_miles[-1] > 0:
            scale = total_miles / cum_miles[-1]
            cum_miles = [m * scale for m in cum_miles]

        # --- Step 4: Detect states offline (reverse_geocoder, 0 API calls) ---
        segments = build_route_segments(coords, cum_miles)

        # --- Step 5: Load fuel prices and optimize stops ---
        prices_by_state = self.fuel_svc.get_prices_by_state()
        fuel_stops = find_optimal_fuel_stops(
            route_segments=segments,
            prices_by_state=prices_by_state,
            total_distance=total_miles,
        )

        # --- Step 6: Calculate summary ---
        from django.conf import settings
        mpg = float(settings.VEHICLE_MPG)
        max_range = float(settings.VEHICLE_RANGE_MILES)
        total_gallons = total_miles / mpg
        total_cost = sum(s["cost"] for s in fuel_stops)
        avg_price = total_cost / sum(s["gallons_purchased"] for s in fuel_stops) if fuel_stops else 0

        # Build OSM directions link for map visualization
        osm_url = (
            f"https://www.openstreetmap.org/directions"
            f"?engine=fossgis_osrm_car"
            f"&route={start_coords[0]:.5f},{start_coords[1]:.5f}"
            f";{end_coords[0]:.5f},{end_coords[1]:.5f}"
        )

        response_data = {
            "route": {
                "start": start_query,
                "end": end_query,
                "start_coordinates": {"lat": start_coords[0], "lon": start_coords[1]},
                "end_coordinates": {"lat": end_coords[0], "lon": end_coords[1]},
                "total_distance_miles": total_miles,
                "total_duration_hours": route["duration_hours"],
                "map_url": osm_url,
                "geometry": {
                    "type": "LineString",
                    "coordinates": route["geojson_coordinates"],
                },
            },
            "fuel_stops": fuel_stops,
            "summary": {
                "total_distance_miles": total_miles,
                "vehicle_range_miles": max_range,
                "vehicle_mpg": mpg,
                "total_gallons_needed": round(total_gallons, 2),
                "total_fuel_cost_usd": round(total_cost, 2),
                "average_price_per_gallon": round(avg_price, 3),
                "number_of_fuel_stops": len(fuel_stops),
                "states_traversed": list(dict.fromkeys(s["state_abbrev"] for s in segments)),
            },
        }

        return Response(response_data, status=status.HTTP_200_OK)


class HealthView(APIView):
    def get(self, request):
        from .services.fuel_prices import _load_dataframe
        df = _load_dataframe()
        return Response({
            "status": "ok",
            "fuel_stations_loaded": len(df),
            "states_covered": df["State"].nunique(),
        })

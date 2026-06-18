"""
Greedy fuel-stop optimizer.

Strategy:
  At each state boundary (decision point), look ahead within tank range:
  - If current state has the cheapest price in range → fill to full.
  - If a cheaper state is reachable → fill just enough to reach it.
  - If we MUST buy fuel to make it to the next decision point → buy minimum needed.

This greedy approach is optimal for the single-vehicle, fixed-route problem.
"""

from django.conf import settings

BUFFER_MILES = 20  # safety buffer when calculating minimum fill


def _split_long_segments(
    segments: list[dict], max_range: float
) -> list[dict]:
    """Split any segment longer than max_range into smaller chunks."""
    result = []
    for seg in segments:
        length = seg["end_mile"] - seg["start_mile"]
        if length <= max_range:
            result.append(seg)
        else:
            pos = seg["start_mile"]
            chunk_size = max_range * 0.85  # 85% of range per chunk
            while pos < seg["end_mile"]:
                chunk_end = min(pos + chunk_size, seg["end_mile"])
                result.append({**seg, "start_mile": pos, "end_mile": chunk_end})
                pos = chunk_end
    return result


def find_optimal_fuel_stops(
    route_segments: list[dict],
    prices_by_state: dict,
    total_distance: float,
    max_range: float = None,
    mpg: float = None,
) -> list[dict]:
    """
    route_segments: output of state_locator.build_route_segments()
    prices_by_state: output of FuelPricesService.get_prices_by_state()
    Returns list of fuel-stop dicts.
    """
    if max_range is None:
        max_range = float(settings.VEHICLE_RANGE_MILES)
    if mpg is None:
        mpg = float(settings.VEHICLE_MPG)

    if not route_segments:
        return []

    # Attach prices and split long segments
    for seg in route_segments:
        state = seg["state_abbrev"]
        if state in prices_by_state:
            seg["price"] = prices_by_state[state]["min_price"]
        else:
            from .fuel_prices import NATIONAL_AVERAGE_PRICE
            seg["price"] = NATIONAL_AVERAGE_PRICE

    segments = _split_long_segments(route_segments, max_range)
    n = len(segments)
    tank = max_range  # start with full tank
    fuel_stops = []

    for i, seg in enumerate(segments):
        current_mile = seg["start_mile"]
        price = seg["price"]

        # Miles remaining to destination from this point
        miles_to_dest = total_distance - current_mile
        if miles_to_dest <= tank:
            # Enough fuel to finish — no more stops needed
            break

        # Next decision point distance
        next_mile = segments[i + 1]["start_mile"] if i + 1 < n else total_distance
        miles_to_next = next_mile - current_mile

        # Mandatory minimum: fuel needed to reach next decision point
        min_fill = max(0.0, miles_to_next - tank + BUFFER_MILES)

        # Lookahead: what prices are available within our max_range from here?
        lookahead = [
            s for s in segments[i + 1:]
            if s["start_mile"] - current_mile <= max_range
        ]

        if not lookahead:
            # No more decision points in range — fill enough to finish
            optimal_fill = max(0.0, miles_to_dest - tank + BUFFER_MILES)
        else:
            min_future_price = min(s["price"] for s in lookahead)

            if price <= min_future_price:
                # Current state is cheapest in range → fill to full
                optimal_fill = max_range - tank
            else:
                # Cheaper fuel ahead — find nearest cheapest
                cheapest_seg = min(lookahead, key=lambda s: s["price"])
                dist_to_cheapest = cheapest_seg["start_mile"] - current_mile

                if dist_to_cheapest <= tank:
                    # Can reach cheapest without buying anything extra
                    optimal_fill = min_fill
                else:
                    # Must buy enough to reach cheapest
                    optimal_fill = dist_to_cheapest - tank + BUFFER_MILES

        fill = max(min_fill, optimal_fill)
        fill = min(fill, max_range - tank)  # can't exceed tank capacity

        if fill >= 1.0:
            gallons = fill / mpg
            cost = gallons * price
            station_info = prices_by_state.get(seg["state_abbrev"], {}).get(
                "cheapest_station"
            )
            fuel_stops.append(
                {
                    "stop_number": len(fuel_stops) + 1,
                    "state": seg["state_abbrev"],
                    "mile_marker": round(current_mile),
                    "lat": seg["entry_lat"],
                    "lon": seg["entry_lon"],
                    "price_per_gallon": round(price, 3),
                    "gallons_purchased": round(gallons, 2),
                    "cost": round(cost, 2),
                    "recommended_station": station_info,
                }
            )
            tank += fill

        # Drive through this segment
        seg_length = seg["end_mile"] - seg["start_mile"]
        tank -= seg_length
        tank = max(tank, 0.0)

    return fuel_stops

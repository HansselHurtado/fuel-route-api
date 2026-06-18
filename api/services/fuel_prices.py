import functools
import pandas as pd
from django.conf import settings


NATIONAL_AVERAGE_PRICE = 3.50  # fallback if state not in dataset


@functools.lru_cache(maxsize=1)
def _load_dataframe() -> pd.DataFrame:
    """Load and cache the fuel prices CSV once at startup."""
    df = pd.read_csv(settings.FUEL_PRICES_CSV)
    df.columns = df.columns.str.strip()
    df["State"] = df["State"].str.strip().str.upper()
    df["Retail Price"] = pd.to_numeric(df["Retail Price"], errors="coerce")
    df = df.dropna(subset=["Retail Price"])
    return df


class FuelPricesService:
    """Loads fuel station prices from CSV and provides per-state aggregates."""

    def get_prices_by_state(self) -> dict[str, dict]:
        """
        Returns {state_abbrev: {'min_price': float, 'avg_price': float, 'cheapest_station': dict}}
        """
        df = _load_dataframe()
        result = {}
        for state, group in df.groupby("State"):
            cheapest_row = group.loc[group["Retail Price"].idxmin()]
            result[state] = {
                "min_price": round(float(group["Retail Price"].min()), 4),
                "avg_price": round(float(group["Retail Price"].mean()), 4),
                "station_count": len(group),
                "cheapest_station": {
                    "name": str(cheapest_row.get("Truckstop Name", "")).strip(),
                    "address": str(cheapest_row.get("Address", "")).strip(),
                    "city": str(cheapest_row.get("City", "")).strip(),
                    "state": state,
                    "price": round(float(cheapest_row["Retail Price"]), 4),
                },
            }
        return result

    def get_state_price(self, state_abbrev: str) -> float:
        """Return the minimum price for a state, or national average if unknown."""
        prices = self.get_prices_by_state()
        state = state_abbrev.upper()
        if state in prices:
            return prices[state]["min_price"]
        return NATIONAL_AVERAGE_PRICE

    def get_cheapest_station(self, state_abbrev: str) -> dict | None:
        prices = self.get_prices_by_state()
        state = state_abbrev.upper()
        if state in prices:
            return prices[state]["cheapest_station"]
        return None

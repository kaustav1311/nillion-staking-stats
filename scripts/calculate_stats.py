# scripts/calculate_stats.py
import requests
import json
import os
from decimal import Decimal, getcontext
from datetime import datetime, timezone

# Set precision for Decimal calculations
getcontext().prec = 50

# --- Configuration ---
NIL_REST_API_BASE = "https://nilchain-api.nillion.network"
INFLATION_ENDPOINT = "/cosmos/mint/v1beta1/inflation"
POOL_ENDPOINT = "/cosmos/staking/v1beta1/pool"
SUPPLY_ENDPOINT = "/cosmos/bank/v1beta1/supply/by_denom?denom=unil"
VALIDATORS_ENDPOINT = "/cosmos/staking/v1beta1/validators?status=BOND_STATUS_BONDED&pagination.limit=1&pagination.count_total=true"

# Output file path (relative to repo root)
OUTPUT_FILE = "data/staking_stats.json"
NIL_DECIMALS = 6
# --- End Configuration ---

def fetch_data(url):
    """Fetches JSON data from a URL with basic error handling."""
    try:
        print(f"Fetching: {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        print(f"  Status Code: {response.status_code}")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from {url}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {url}: {e}")
        return None

def calculate_stats():
    """Fetches Nillion chain data and calculates staking stats."""
    print(f"--- Starting Stat Calculation: {datetime.now(timezone.utc).isoformat()} ---")
    stats = {
        "calculated_apr_percentage": None,
        "total_staked_nil": None,
        "active_validator_count": None,
        "raw_inflation_rate": None,
        "raw_total_supply_unil": None,
        "raw_bonded_tokens_unil": None,
    }
    inflation_rate = None
    bonded_tokens_unil = None
    total_supply_unil = None

    print("\nFetching Inflation...")
    inflation_data = fetch_data(NIL_REST_API_BASE + INFLATION_ENDPOINT)
    if inflation_data and 'inflation' in inflation_data:
        try:
            inflation_rate_str = inflation_data['inflation']
            inflation_rate = Decimal(inflation_rate_str)
            stats["raw_inflation_rate"] = inflation_rate_str
            print(f"  Inflation Rate: {inflation_rate}")
        except Exception as e:
            print(f"  Error processing inflation rate: {e}")
    else:
        print("  Failed to fetch or parse inflation data.")

    print("\nFetching Staking Pool...")
    pool_data = fetch_data(NIL_REST_API_BASE + POOL_ENDPOINT)
    if pool_data and 'pool' in pool_data and 'bonded_tokens' in pool_data['pool']:
        try:
            bonded_tokens_str = pool_data['pool']['bonded_tokens']
            bonded_tokens_unil = Decimal(bonded_tokens_str)
            stats["raw_bonded_tokens_unil"] = bonded_tokens_str
            print(f"  Bonded Tokens (unil): {bonded_tokens_unil}")
            stats["total_staked_nil"] = float(bonded_tokens_unil / (Decimal(10)**NIL_DECIMALS))
            print(f"  Total Staked NIL: {stats['total_staked_nil']:.2f}")
        except Exception as e:
            print(f"  Error processing bonded tokens: {e}")
    else:
        print("  Failed to fetch or parse staking pool data.")

    print("\nFetching Total Supply...")
    supply_data = fetch_data(NIL_REST_API_BASE + SUPPLY_ENDPOINT)
    if supply_data and 'amount' in supply_data and 'amount' in supply_data['amount']:
         try:
            total_supply_str = supply_data['amount']['amount']
            total_supply_unil = Decimal(total_supply_str)
            stats["raw_total_supply_unil"] = total_supply_str
            print(f"  Total Supply (unil): {total_supply_unil}")
         except Exception as e:
            print(f"  Error processing total supply: {e}")
    else:
         print("  Failed to fetch or parse total supply data.")

    print("\nFetching Validator Count...")
    validators_data = fetch_data(NIL_REST_API_BASE + VALIDATORS_ENDPOINT)
    if validators_data and 'pagination' in validators_data and 'total' in validators_data['pagination']:
         try:
            stats["active_validator_count"] = int(validators_data['pagination']['total'])
            print(f"  Active Validator Count: {stats['active_validator_count']}")
         except Exception as e:
            print(f"  Error processing validator count: {e}")
    else:
         print("  Failed to fetch or parse validator count.")

    print("\nCalculating APR...")
    if inflation_rate is not None and total_supply_unil is not None and bonded_tokens_unil is not None:
        if bonded_tokens_unil > 0:
            try:
                raw_apr = (inflation_rate * total_supply_unil) / bonded_tokens_unil
                apr_percentage = raw_apr * 100
                stats["calculated_apr_percentage"] = float(f"{apr_percentage:.4f}")
                print(f"  Calculated APR: {stats['calculated_apr_percentage']}%")
            except Exception as e:
                print(f"  Error calculating APR: {e}")
        else:
            print("  Cannot calculate APR because bonded tokens is zero.")
            stats["calculated_apr_percentage"] = 0.0
    else:
        print("  Skipping APR calculation due to missing prerequisite data.")

    print(f"\n--- Stat Calculation Finished ---")
    return stats

def save_stats_to_file(stats_data):
    """Saves the calculated stats to a JSON file, checking for changes first."""
    if stats_data is None:
        print("No stats data provided to save.")
        return

    script_dir = os.path.dirname(__file__)
    # Path is relative to repo root: data/staking_stats.json
    output_path = os.path.join(script_dir, '..', OUTPUT_FILE)
    output_path = os.path.normpath(output_path)

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    stats_data["last_updated_utc"] = datetime.now(timezone.utc).isoformat()

    try:
        existing_data = {}
        if os.path.exists(output_path):
             with open(output_path, 'r') as f:
                  try:
                      existing_data = json.load(f)
                  except json.JSONDecodeError:
                      print(f"Existing data file {output_path} is invalid. Overwriting.")

        relevant_keys = [
            "calculated_apr_percentage", "total_staked_nil", "active_validator_count",
            "raw_inflation_rate", "raw_total_supply_unil", "raw_bonded_tokens_unil"
        ]
        has_changed = False
        if not existing_data:
            has_changed = True
        else:
            for k in relevant_keys:
                if stats_data.get(k) != existing_data.get(k):
                    has_changed = True
                    print(f"Detected change in '{k}': '{existing_data.get(k)}' -> '{stats_data.get(k)}'")
                    break

        if not has_changed:
             print(f"Data hasn't changed significantly. Skipping file write to {output_path}.")
             return

        with open(output_path, 'w') as f:
            json.dump(stats_data, f, indent=2)
        print(f"Successfully saved stats to {output_path}")

    except IOError as e:
        print(f"Error writing stats to file {output_path}: {e}")
    except TypeError as e:
         print(f"Error serializing stats data to JSON: {e} - Data: {stats_data}")

if __name__ == "__main__":
    calculated_stats = calculate_stats()
    save_stats_to_file(calculated_stats)

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
# Endpoint to get bonded validators count efficiently
VALIDATORS_ENDPOINT = "/cosmos/staking/v1beta1/validators?status=BOND_STATUS_BONDED&pagination.limit=1&pagination.count_total=true"

# Output file path (relative to repository root)
OUTPUT_FILE = "public/data/staking_stats.json"
NIL_DECIMALS = 6 # Assumes 1 NIL = 1,000,000 unil
# --- End Configuration ---

def fetch_data(url):
    """Fetches JSON data from a URL with basic error handling."""
    try:
        print(f"Fetching: {url}")
        # Increased timeout for potentially slower API endpoints
        response = requests.get(url, timeout=30)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
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
        "active_validator_count": None
    }
    # Values needed for calculation
    inflation_rate = None
    bonded_tokens_unil = None
    total_supply_unil = None

    # 1. Fetch Inflation
    print("\nFetching Inflation...")
    inflation_data = fetch_data(NIL_REST_API_BASE + INFLATION_ENDPOINT)
    if inflation_data and 'inflation' in inflation_data:
        try:
            inflation_rate = Decimal(inflation_data['inflation'])
            print(f"  Inflation Rate: {inflation_rate}")
        except Exception as e:
            print(f"  Error processing inflation rate: {e}")
    else:
        print("  Failed to fetch or parse inflation data.")

    # 2. Fetch Staking Pool data (Bonded Tokens)
    print("\nFetching Staking Pool...")
    pool_data = fetch_data(NIL_REST_API_BASE + POOL_ENDPOINT)
    if pool_data and 'pool' in pool_data and 'bonded_tokens' in pool_data['pool']:
        try:
            bonded_tokens_unil = Decimal(pool_data['pool']['bonded_tokens'])
            print(f"  Bonded Tokens (unil): {bonded_tokens_unil}")
            # Convert to NIL for saving
            stats["total_staked_nil"] = float(bonded_tokens_unil / (Decimal(10)**NIL_DECIMALS))
            print(f"  Total Staked NIL: {stats['total_staked_nil']:.2f}")
        except Exception as e:
            print(f"  Error processing bonded tokens: {e}")
    else:
        print("  Failed to fetch or parse staking pool data.")

    # 3. Fetch Total Supply
    print("\nFetching Total Supply...")
    supply_data = fetch_data(NIL_REST_API_BASE + SUPPLY_ENDPOINT)
    if supply_data and 'amount' in supply_data and 'amount' in supply_data['amount']:
         try:
            total_supply_unil = Decimal(supply_data['amount']['amount'])
            print(f"  Total Supply (unil): {total_supply_unil}")
         except Exception as e:
            print(f"  Error processing total supply: {e}")
    else:
         print("  Failed to fetch or parse total supply data.")

    # 4. Fetch Validator Count
    print("\nFetching Validator Count...")
    validators_data = fetch_data(NIL_REST_API_BASE + VALIDATORS_ENDPOINT)
    if validators_data and 'pagination' in validators_data and 'total' in validators_data['pagination']:
         try:
            stats["active_validator_count"] = int(validators_data['pagination']['total'])
            print(f"  Active Validator Count: {stats['active_validator_count']}")
         except Exception as e:
            print(f"  Error processing validator count: {e}")
    else:
         print("  Failed to fetch or parse validator count (pagination total might be missing).")


    # 5. Calculate APR (only if all necessary components were fetched successfully)
    print("\nCalculating APR...")
    if inflation_rate is not None and total_supply_unil is not None and bonded_tokens_unil is not None:
        if bonded_tokens_unil > 0:
            try:
                # Basic formula: APR = (Inflation Rate * Total Supply) / Total Bonded Tokens
                # Consider fetching community_tax from /cosmos/distribution/v1beta1/params if needed
                # community_tax_rate = Decimal(dist_params_data['params']['community_tax'])
                # effective_inflation = inflation_rate * (1 - community_tax_rate)
                # raw_apr = (effective_inflation * total_supply_unil) / bonded_tokens_unil

                raw_apr = (inflation_rate * total_supply_unil) / bonded_tokens_unil
                apr_percentage = raw_apr * 100
                stats["calculated_apr_percentage"] = float(f"{apr_percentage:.4f}") # Round for consistency
                print(f"  Calculated APR: {stats['calculated_apr_percentage']}%")
            except Exception as e:
                print(f"  Error calculating APR: {e}")
        else:
            print("  Cannot calculate APR because bonded tokens is zero.")
            stats["calculated_apr_percentage"] = 0.0
    else:
        print("  Skipping APR calculation due to missing prerequisite data.")

    print(f"\n--- Stat Calculation Finished ---")
    return stats # Return the dictionary containing all stats

def save_stats_to_file(stats_data):
    """Saves the calculated stats to a JSON file."""
    if stats_data is None:
        print("No stats data provided to save.")
        return

    # Ensure the directory exists
    output_dir = os.path.dirname(OUTPUT_FILE)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Add timestamp
    stats_data["last_updated_utc"] = datetime.now(timezone.utc).isoformat()

    # Read existing data if file exists, to only update if values change
    # This helps prevent unnecessary commits in the workflow
    try:
        with open(OUTPUT_FILE, 'r') as f:
            existing_data = json.load(f)
        # Compare relevant fields, ignore timestamp for change detection
        relevant_keys = ["calculated_apr_percentage", "total_staked_nil", "active_validator_count"]
        if all(existing_data.get(k) == stats_data.get(k) for k in relevant_keys):
             print(f"Data hasn't changed significantly. Skipping file write to {OUTPUT_FILE}.")
             return # Exit without writing if data is the same
    except (FileNotFoundError, json.JSONDecodeError):
        print("No existing data file found or file is invalid. Writing new file.")
        pass # Continue to write the file if it doesn't exist or is invalid

    try:
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(stats_data, f, indent=2)
        print(f"Successfully saved stats to {OUTPUT_FILE}")
    except IOError as e:
        print(f"Error writing stats to file {OUTPUT_FILE}: {e}")
    except TypeError as e:
         print(f"Error serializing stats data to JSON: {e} - Data: {stats_data}")

# --- Main Execution ---
if __name__ == "__main__":
    calculated_stats = calculate_stats()
    save_stats_to_file(calculated_stats)

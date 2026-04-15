"""
Seed historical price data from IB for all instruments in the IB config.

Wraps seed_price_data_from_IB to loop through every instrument configured
in sysbrokers/IB/config/ib_config_futures.csv.

Safe to re-run — existing data is not overwritten, only missing data is fetched.

Usage:
    python -m sysinit.futures.seed_all_prices_from_IB

This will take several hours. If interrupted, re-run and it will pick up
where it left off (instruments already downloaded are skipped).
"""

import time
from syscore.exceptions import missingInstrument
from sysbrokers.IB.config.ib_instrument_config import (
    read_ib_config_from_file,
    get_instrument_list_from_ib_config,
)
from sysinit.futures.seed_price_data_from_IB import seed_price_data_from_IB


def get_all_ib_instrument_codes() -> list:
    config = read_ib_config_from_file()
    return get_instrument_list_from_ib_config(config)


def seed_all_prices(instrument_codes: list):
    total = len(instrument_codes)
    failed = []

    for i, instrument_code in enumerate(instrument_codes, start=1):
        print(f"\n[{i}/{total}] Seeding {instrument_code} ...")
        try:
            seed_price_data_from_IB(instrument_code)
        except missingInstrument:
            print(f"  SKIP — {instrument_code} not found in IB config")
            failed.append(instrument_code)
        except KeyboardInterrupt:
            print("\nInterrupted. Re-run to continue — completed instruments are safe.")
            break
        except Exception as exc:
            print(f"  ERROR — {instrument_code}: {exc}")
            failed.append(instrument_code)
            # brief pause before continuing to next instrument
            time.sleep(2)

    if failed:
        print(f"\nFailed instruments ({len(failed)}):")
        for code in failed:
            print(f"  {code}")
        print("\nRe-run the script to retry failed instruments.")
    else:
        print("\nAll instruments seeded successfully.")


if __name__ == "__main__":
    print("Seed historical price data from IB for all configured instruments.")
    print("This will take several hours. Press Ctrl-C at any time to pause safely.\n")

    instrument_codes = get_all_ib_instrument_codes()
    print(f"Found {len(instrument_codes)} instruments in IB config.\n")

    seed_all_prices(instrument_codes)

"""
Build roll calendars from downloaded price data for all instruments.

Usage:
    python -m sysinit.futures.rollcalendars_from_db_prices_to_csv_all
"""

from sysproduction.data.prices import diagPrices
from sysinit.futures.rollcalendars_from_db_prices_to_csv import build_and_write_roll_calendar
from syscore.constants import arg_not_supplied


def get_instruments_with_prices() -> list:
    diag_prices = diagPrices()
    contracts = diag_prices.db_futures_contract_price_data.get_contracts_with_merged_price_data()
    return sorted(set(c.instrument_code for c in contracts))


def build_all_roll_calendars():
    instruments = get_instruments_with_prices()
    total = len(instruments)
    print(f"Building roll calendars for {total} instruments...\n")

    failed = []
    for i, code in enumerate(instruments, start=1):
        print(f"[{i}/{total}] {code}")
        try:
            build_and_write_roll_calendar(
                code,
                output_datapath=arg_not_supplied,
                check_before_writing=False,
            )
        except KeyboardInterrupt:
            print("\nInterrupted. Re-run to continue.")
            break
        except Exception as exc:
            print(f"  ERROR — {code}: {exc}")
            failed.append((code, str(exc)))

    if failed:
        print(f"\nFailed ({len(failed)}):")
        for code, err in failed:
            print(f"  {code}: {err}")
    else:
        print("\nAll roll calendars built successfully.")


if __name__ == "__main__":
    build_all_roll_calendars()

"""
Run update_sampled_contracts for all instruments, skipping those that fail.

This is needed on fresh installs where multiple prices data is stale and
contract objects don't yet exist in MongoDB.

Usage:
    python -m sysinit.futures.update_sampled_contracts_all
"""

from sysdata.data_blob import dataBlob
from sysproduction.update_sampled_contracts import update_active_contracts_for_instrument
from sysproduction.data.prices import diagPrices


def run():
    data = dataBlob()
    diag = diagPrices(data)
    instruments = diag.db_futures_multiple_prices_data.get_list_of_instruments()
    total = len(instruments)
    failed = []

    print(f"Updating sampled contracts for {total} instruments...\n")

    for i, code in enumerate(instruments, 1):
        print(f"[{i}/{total}] {code}", end=" ... ", flush=True)
        try:
            update_active_contracts_for_instrument(code, data)
            print("OK")
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break
        except Exception as exc:
            print(f"SKIP ({exc})")
            failed.append((code, str(exc)))

    if failed:
        print(f"\nFailed ({len(failed)}):")
        for code, err in failed:
            print(f"  {code}: {err}")
    else:
        print("\nAll instruments updated.")


if __name__ == "__main__":
    run()

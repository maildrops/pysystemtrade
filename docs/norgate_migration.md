# Migrating Historical Price Data from IB to Norgate

This guide replaces the IB historical data seed layer with
[Norgate](https://norgatedata.com/) professional futures data using the
[norgate-pst-utils](https://github.com/maildrops/norgate-pst-utils) bridge
repo.

**What changes:** contract prices, roll calendars, multiple prices, adjusted
prices — all rebuilt from Norgate CSV exports.

**What stays the same:** MongoDB (capital, orders, positions, logs), IB
Gateway, `private_config.yaml`, crontab, strategy config, FX prices. IB
continues to be used for live daily price top-ups after migration.

**Prerequisites:**
- Norgate Data subscription (professional futures tier)
- Norgate Data Updater installed and synced on Windows
- Windows machine on the same local network as the Pi (e.g. Parallels VM on the same Mac)
- `samba` on the Pi (`sudo apt install -y samba`)

**Time estimate:** 2–4 hours total (export ~30 min, import ~60–90 min, rebuild
~30–60 min)

---

## Quick Checklist

- [ ] [Phase 1](#phase-1-share-a-pi-directory-to-windows-via-samba) — Share a Pi directory to Windows via Samba
- [ ] [Phase 2](#phase-2-export-norgate-data-on-windows) — Export ~23,000 CSV files on Windows
- [ ] [Phase 3](#phase-3-clear-existing-price-data) — Clear IB Parquet data (keep MongoDB)
- [ ] [Phase 4](#phase-4-import-norgate-prices-into-parquet) — Import Norgate CSVs into Parquet
- [ ] [Phase 5](#phase-5-rebuild-roll-calendars) — Rebuild roll calendars from new prices
- [ ] [Phase 6](#phase-6-rebuild-multiple-prices) — Rebuild multiple prices
- [ ] [Phase 7](#phase-7-rebuild-adjusted-prices) — Rebuild adjusted prices
- [ ] [Phase 8](#phase-8-update-sampled-contracts) — Update sampled contracts in MongoDB
- [ ] [Phase 9](#phase-9-verify) — Verify with a backtest

---

## Phase 1: Share a Pi Directory to Windows via Samba

The cleanest approach is to export a directory on the Pi via Samba and map it
as a drive letter on Windows. The Norgate export then writes directly to the
Pi's filesystem — no transfer step required.

### 1a — Set up Samba on the Pi

```bash
sudo apt install -y samba
mkdir -p ~/norgate_export
```

Add the following stanza to `/etc/samba/smb.conf` (append to the end of the
file):

```ini
[norgate_export]
path = /home/djb/norgate_export
browseable = yes
read only = no
guest ok = no
```

Then set a Samba password for your Pi user and restart the service:

```bash
sudo smbpasswd -a djb
sudo systemctl restart smbd
```

Find your Pi's IP address:

```bash
hostname -I
# e.g. 192.168.0.x
```

### 1b — Map the Pi share on Windows

Open PowerShell on the Windows machine and map the Pi share to a free drive
letter (C: is taken; use any available letter, e.g. P:):

```powershell
net use P: \\192.168.0.x\norgate_export /user:djb YOUR_SAMBA_PASSWORD
```

Verify the mapping:

```powershell
dir P:\
# Should show an empty directory initially
```

---

## Phase 2: Export Norgate Data on Windows

Run these steps on the **Windows machine** (Parallels VM or native).

1. Open PowerShell and clone the bridge repo:

   ```powershell
   git clone https://github.com/maildrops/norgate-pst-utils.git
   cd norgate-pst-utils
   pip install norgatedata pandas
   ```

2. Confirm Norgate Data Updater is running and fully synced (check the
   system tray icon — it should show a green tick with today's date).

3. Run the export, pointing the output at the mapped Pi drive:

   ```powershell
   python norgate_utils/export.py --output-dir P:\
   ```

   This writes approximately 23,000 CSV files named
   `{INSTRUMENT}_{YYYYMM00}.csv` with columns
   `DATETIME, OPEN, HIGH, LOW, FINAL, VOLUME`. Price unit corrections
   (JPY÷100, SILVER, COPPER) are applied automatically by `export.py` —
   no Pi-side action needed.

   Expect this to take 20–40 minutes for 105 instruments.

4. When the export completes, the files are already on the Pi at
   `~/norgate_export/norgate_export`. You can disconnect the Windows
   drive mapping:

   ```powershell
   net use P: /delete
   ```

---

## Phase 3: Clear Existing Price Data

This removes only the Parquet price store. MongoDB (capital, orders,
positions, FX prices, logs) is **not touched**.

```bash
# Remove contract prices, multiple prices, and adjusted prices
rm -rf ~/data/parquet/futures_contract_prices/
rm -rf ~/data/parquet/futures_multiple_prices/
rm -rf ~/data/parquet/futures_adjusted_prices/

# Remove old roll calendars (will be rebuilt from Norgate data)
rm -f ~/pysystemtrade/data/futures/roll_calendars_csv/*.csv
```

> **Do not** delete `~/data/parquet/fx_prices_data/` — FX prices remain
> seeded from IB.

---

## Phase 4: Import Norgate Prices into Parquet

Run from the Pi in the `pysystemtrade` virtualenv:

```bash
cd ~/pysystemtrade
python -c "
from sysinit.futures.contract_prices_from_csv_to_db import init_db_with_csv_futures_contract_prices
init_db_with_csv_futures_contract_prices('/home/djb/norgate_export/norgate_export')
"
```

When prompted, press Enter to confirm. The importer reads each
`{INSTRUMENT}_{YYYYMM00}.csv` file and writes daily prices to Parquet.
This replaces the 12-hour IB bulk download with a fast local file read —
expect 60–90 minutes for 105 instruments.

> **Note:** The path has two `norgate_export` components because `export.py`
> creates a subdirectory inside the Samba share root. Adjust if your export
> wrote directly to the share root (`~/norgate_export`).

**Script:** `sysinit/futures/contract_prices_from_csv_to_db.py`
**Key function:** `init_db_with_csv_futures_contract_prices(datapath)`

---

## Phase 5: Rebuild Roll Calendars

With clean Norgate data covering ~40 years per instrument, roll calendar
construction is far more reliable than with IB data.

```bash
cd ~/pysystemtrade
python -m sysinit.futures.rollcalendars_from_db_prices_to_csv_all
```

This iterates over all instruments that have price data in Parquet,
builds roll calendars from the price transitions, and writes them to
`data/futures/roll_calendars_csv/`. Instruments that fail (e.g. insufficient
price history) are skipped with an error message and a summary is printed at
the end.

**Script:** `sysinit/futures/rollcalendars_from_db_prices_to_csv_all.py`

---

## Phase 6: Rebuild Multiple Prices

```bash
cd ~/pysystemtrade
python -m sysinit.futures.multipleprices_from_db_prices_and_csv_calendars_to_db
```

Confirm at the prompt. This stitches contract prices together using the roll
calendars from Phase 5 and writes the result to Parquet. Instruments without
a valid roll calendar are skipped; a failed-instrument list is printed at the
end.

**Script:** `sysinit/futures/multipleprices_from_db_prices_and_csv_calendars_to_db.py`

---

## Phase 7: Rebuild Adjusted Prices

```bash
cd ~/pysystemtrade
python -m sysinit.futures.adjustedprices_from_db_multiple_to_db
```

Confirm at the prompt. Instruments with empty multiple prices (e.g. due to
failed roll calendar) are skipped.

**Script:** `sysinit/futures/adjustedprices_from_db_multiple_to_db.py`

---

## Phase 8: Update Sampled Contracts

This tells the system which contracts are currently active and should receive
live price top-ups from IB via the daily cron job.

```bash
cd ~/pysystemtrade
python -m sysinit.futures.update_sampled_contracts_all
```

This runs `update_active_contracts_for_instrument` for every instrument that
has multiple prices, skipping any that fail with `ContractNotFound` (expected
for instruments where the most-recent contract isn't yet in MongoDB).

**Script:** `sysinit/futures/update_sampled_contracts_all.py`

---

## Phase 9: Verify

### Check instrument counts

```python
from sysproduction.data.prices import diagPrices
d = diagPrices()
print('Contract prices:  ', len(d.db_futures_contract_price_data.get_list_of_instrument_codes_with_merged_price_data()), 'instruments')
print('Multiple prices:  ', len(d.db_futures_multiple_prices_data.get_list_of_instruments()), 'instruments')
print('Adjusted prices:  ', len(d.db_futures_adjusted_prices_data.get_list_of_instruments()), 'instruments')
```

Expect approximately 100 instruments across all three levels (vs 105 exported
— a small number will fail roll calendar or multiple prices construction).

### Run a backtest

```python
from systems.provided.rob_system.run_system import futures_system
s = futures_system()
print(s.portfolio.get_notional_position('AEX').tail())
```

The dates in the output should be current (today's date, not 2024).
No `missingData` or `ContractNotFound` errors should appear for instruments
in the backtest.

### Confirm daily cron is still working

After the next scheduled run of `run_daily_price_updates`, check the echo
file:

```bash
tail -50 ~/data/echos/run_daily_price_updates.txt
```

IB will continue to top up prices for sampled contracts from today onward.
There should be no conflicts with the Norgate historical seed.

---

## Notes

| Topic | Detail |
|---|---|
| **Price corrections** | JPY÷100, SILVER, COPPER handled in `export.py` on the Windows side — no Pi action needed |
| **FX prices** | Not affected — still seeded from IB CSV / `update_fx_prices` |
| **MongoDB** | Capital, orders, positions, logs — all untouched |
| **105 vs 179 instruments** | The ~74 instruments in `rob_system` not covered by Norgate should be added to `exclude_instrument_lists.ignore_instruments` in `private_config.yaml` to avoid backtest errors |
| **IB Gateway** | Still used for live daily top-ups via `run_daily_price_updates` |
| **Re-running phases** | Phases 5–8 are safe to re-run if a phase fails partway through — existing data is overwritten |

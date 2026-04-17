# pysystemtrade Setup Runsheet — Raspberry Pi 5 + IB Paper Trading

Quick-reference for reproducing a fresh install. Assumes Raspberry Pi 5, Linux ARM64, 
IB Gateway already installed.

---

## Prerequisites (one-time system installs)

```bash
# MongoDB
sudo apt install -y mongodb
sudo systemctl enable --now mongodb

# git, uv
sudo apt install -y git
curl -Ls https://astral.sh/uv/install.sh | sh
```

---

## 1. Clone the repo

```bash
cd ~
git clone https://github.com/maildrops/pysystemtrade.git
cd pysystemtrade
git checkout claude/document-repo-overview-nGaSU
```

---

## 2. Virtual environment and dependencies

```bash
uv venv .venv --python 3.10
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install -e .
```

Add to `~/.bashrc` for convenience:
```bash
alias pst='cd ~/pysystemtrade && source .venv/bin/activate'
```

---

## 3. Run the interactive setup script

```bash
python -m sysinit.setup_live_trading
```

Prompts you for:
- IB broker account number (e.g. `DU12345` for paper)
- Parquet store path (e.g. `~/data/parquet`)
- MongoDB data path (e.g. `~/data/mongodb`)
- Base currency (e.g. `AUD`)
- IB Gateway IP and port (e.g. `127.0.0.1`, `4002` for paper)

Creates directories, writes `private/private_config.yaml`, seeds spread costs and 
static CSV prices into MongoDB/Parquet.

After it finishes:
```bash
source ~/.profile
```

---

## 4. Start IB Gateway

- Open IB Gateway in paper trading mode
- Enable API connections: port `4002` (paper), `4001` (live)
- Recommended: use IBC for auto-login

---

## 5. Bulk historical price download from IB

Run inside a `screen` session — takes 12–24 hours.

```bash
screen -S pysystemtrade
python -m sysinit.futures.seed_all_prices_from_IB
# Ctrl-A D  → detach (keeps running)
# screen -r pysystemtrade  → reattach later
```

Safe to interrupt and re-run — already-downloaded instruments are skipped.

---

## 6. Build roll calendars from downloaded prices

```bash
python -m sysinit.futures.rollcalendars_from_db_prices_to_csv_all
```

Expect ~471/584 instruments to succeed. Failures are obscure instruments with 
no roll parameters defined — safe to ignore.

---

## 7. Build multiple prices

```bash
python -m sysinit.futures.multipleprices_from_db_prices_and_csv_calendars_to_db
```

Press Enter to confirm when prompted. Takes a few minutes.

---

## 8. Build back-adjusted prices

```bash
python -m sysinit.futures.adjustedprices_from_db_multiple_to_db
```

Press Enter to confirm. Some instruments will be skipped (empty data) — normal.

---

## Done — data bootstrap complete

You now have in local storage:
- Raw contract prices → Parquet
- Roll calendars → CSV
- Multiple prices → Parquet  
- Back-adjusted prices → Parquet

**Next steps:** configure strategy, install crontab, start paper trading.

---

## Useful commands

```bash
# Check MongoDB is running
sudo systemctl status mongodb

# Reattach to screen session
screen -r pysystemtrade

# List all screen sessions
screen -ls

# Verify instrument list
python -c "from sysproduction.data.prices import diagPrices; p = diagPrices(); print(len(p.db_futures_multiple_prices_data.get_list_of_instruments()), 'instruments with multiple prices')"
```

---

## IB Gotchas

| Problem | Cause | Fix |
|---|---|---|
| `Error 162` — different IP | TWS/Gateway running on another machine with same IB username | Close the other session |
| `missingInstrument` | Using IB ticker (e.g. `MES`) instead of pysystemtrade name (`SP500_micro`) | Check `sysbrokers/IB/config/ib_config_futures.csv` column 1 |
| Hourly data warnings | Thinly traded instrument | Normal — daily data still downloads |
| `Empty roll calendar after adjustment` | Using shipped CSV roll calendars with fresh IB prices | Use `rollcalendars_from_db_prices_to_csv_all` instead |

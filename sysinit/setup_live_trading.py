"""
pysystemtrade live trading setup script.

Automates the mechanical steps of getting pysystemtrade configured for live
trading with Interactive Brokers. Run this after installing pysystemtrade and
activating your virtual environment.

Usage:
    python -m sysinit.setup_live_trading

What this script does:
    1. Collects your configuration values interactively
    2. Creates the required directory structure
    3. Adds environment variables to ~/.profile
    4. Writes private/private_config.yaml
    5. Makes production scripts executable
    6. Seeds static data from shipped CSVs into MongoDB/Parquet
    7. Optionally installs the production crontab

What requires manual action afterward (listed at the end):
    - IB Gateway GUI configuration
    - Historical contract price download from IB (takes hours)
    - Roll calendar generation
    - Strategy configuration and backtesting
    - Capital initialisation and going live
"""

import subprocess
import sys
import textwrap
from pathlib import Path


PYSYS_CODE = Path(__file__).resolve().parent.parent

SEPARATOR = "=" * 70


# ── output helpers ────────────────────────────────────────────────────────────


def section(title: str):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)
    print()


def ok(msg: str):
    print(f"  [OK]   {msg}")


def warn(msg: str):
    print(f"  [WARN] {msg}")


def step(msg: str):
    print(f"  -->    {msg}")


# ── input helpers ─────────────────────────────────────────────────────────────


def ask(prompt: str, default: str = "") -> str:
    """Prompt for a string value, returning default on empty input."""
    if default:
        result = input(f"  {prompt} [{default}]: ").strip()
        return result or default
    while True:
        result = input(f"  {prompt}: ").strip()
        if result:
            return result
        print("  This field is required.")


def yes_no(prompt: str, default: bool = True) -> bool:
    """Prompt for yes/no, returning default on empty input."""
    suffix = " [Y/n]: " if default else " [y/N]: "
    result = input(f"  {prompt}{suffix}").strip().lower()
    if not result:
        return default
    return result.startswith("y")


# ── phase 1: gather configuration ─────────────────────────────────────────────


def phase_config() -> dict:
    section("STEP 1/7 — Configuration")
    print(
        "  Collecting values for private/private_config.yaml.\n"
        "  Press RETURN to accept the default shown in [brackets].\n"
    )

    home = Path.home()

    broker_account = ask(
        "Your IBKR account number  (paper: starts with DU, live: starts with U)"
    )
    parquet_store = ask(
        "Parquet data directory", str(home / "data" / "parquet")
    )
    mongo_data = ask(
        "MongoDB data directory", str(home / "data" / "mongodb")
    )
    backup_dir = ask(
        "Off-system backup directory", str(home / "data" / "backups_offsite")
    )
    base_currency = ask("Base currency of your account (USD, GBP, EUR …)", "USD")
    ib_ipaddress = ask("IB Gateway IP address", "127.0.0.1")
    ib_port = ask("IB Gateway port", "4001")
    echo_path = ask("Echo/log output directory", str(home / "echos"))

    email_address = email_pwd = email_server = ""
    print()
    if yes_no(
        "Configure email alerts now? (optional — can be added later)", default=False
    ):
        email_address = ask("Email address")
        email_pwd = ask("Email password / app password")
        email_server = ask("Outgoing SMTP server", "smtp.gmail.com")

    return {
        "broker_account": broker_account,
        "parquet_store": parquet_store,
        "mongo_data": mongo_data,
        "backup_dir": backup_dir,
        "base_currency": base_currency,
        "ib_ipaddress": ib_ipaddress,
        "ib_port": ib_port,
        "echo_path": echo_path,
        "email_address": email_address,
        "email_pwd": email_pwd,
        "email_server": email_server,
    }


# ── phase 2: directories ──────────────────────────────────────────────────────


def phase_directories(config: dict):
    section("STEP 2/7 — Creating directories")

    home = Path.home()
    dirs = [
        Path(config["parquet_store"]),
        Path(config["mongo_data"]),
        Path(config["echo_path"]),
        home / "data" / "mongo_dump",
        home / "data" / "backups_csv",
        home / "data" / "backtests",
        home / "data" / "reports",
        Path(config["backup_dir"]),
        PYSYS_CODE / "private",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        ok(str(d))


# ── phase 3: environment variables ───────────────────────────────────────────


def phase_env_vars(config: dict):
    section("STEP 3/7 — Environment variables (~/.profile)")

    profile_path = Path.home() / ".profile"
    marker = "# pysystemtrade — added by setup_live_trading.py"

    existing = profile_path.read_text() if profile_path.exists() else ""

    if marker in existing:
        warn(f"{profile_path} already contains pysystemtrade env vars — skipping.")
        warn("Edit the file manually if you need to update paths.")
        return

    block = textwrap.dedent(
        f"""
        {marker}
        export PYSYS_CODE={PYSYS_CODE}
        export MONGO_DATA={config["mongo_data"]}
        export SCRIPT_PATH={PYSYS_CODE}/sysproduction/linux/scripts
        export ECHO_PATH={config["echo_path"]}
        export MONGO_BACKUP_PATH={config["backup_dir"]}
        export PYSYS_LOGGING_CONFIG=syslogging.logging_prod.yaml
        export PATH=$PATH:{PYSYS_CODE}/sysproduction/linux/scripts
        """
    )

    with profile_path.open("a") as f:
        f.write(block)

    ok(f"Environment variables written to {profile_path}")
    print(f"\n  Action required: run   source {profile_path}   (or re-login)")


# ── phase 4: private_config.yaml ─────────────────────────────────────────────


def phase_private_config(config: dict):
    section("STEP 4/7 — Writing private/private_config.yaml")

    config_path = PYSYS_CODE / "private" / "private_config.yaml"

    if config_path.exists():
        if not yes_no(f"{config_path} already exists. Overwrite?", default=False):
            warn("Skipping — using existing private_config.yaml.")
            return

    if config["email_address"]:
        email_block = textwrap.dedent(
            f"""
            # Email alerts
            email_address: '{config["email_address"]}'
            email_pwd: '{config["email_pwd"]}'
            email_server: '{config["email_server"]}'
            """
        )
    else:
        email_block = textwrap.dedent(
            """
            # Email alerts — uncomment and fill in to enable
            # email_address: 'you@example.com'
            # email_pwd: 'your_app_password'
            # email_server: 'smtp.gmail.com'
            """
        )

    content = textwrap.dedent(
        f"""\
        # private_config.yaml
        # Generated by sysinit/setup_live_trading.py
        # This file is excluded from git — keep it safe.

        # ── REQUIRED ─────────────────────────────────────────────────────────
        # Your IBKR account number.
        # Paper accounts start with DU (e.g. DU1234567).
        # Live accounts start with U  (e.g. U1234567).
        broker_account: '{config["broker_account"]}'

        # Directory for Parquet time-series price data.
        parquet_store: '{config["parquet_store"]}'

        # ── IB GATEWAY ───────────────────────────────────────────────────────
        ib_ipaddress: '{config["ib_ipaddress"]}'
        ib_port: {config["ib_port"]}
        ib_idoffset: 1
        {email_block}
        # ── MONGODB ──────────────────────────────────────────────────────────
        mongo_host: 'localhost'
        mongo_db: 'production'

        # ── BACKUPS ──────────────────────────────────────────────────────────
        offsystem_backup_directory: '{config["backup_dir"]}'

        # ── TRADING ──────────────────────────────────────────────────────────
        # Base currency of your trading account.
        base_currency: '{config["base_currency"]}'
        """
    )

    config_path.write_text(content)
    ok(f"Written: {config_path}")


# ── phase 5: make scripts executable ─────────────────────────────────────────


def phase_make_scripts_executable():
    section("STEP 5/7 — Making production scripts executable")

    scripts_dir = PYSYS_CODE / "sysproduction" / "linux" / "scripts"
    if not scripts_dir.exists():
        warn(f"Scripts directory not found: {scripts_dir}")
        return

    script_paths = [str(p) for p in scripts_dir.iterdir() if p.is_file()]
    if not script_paths:
        warn("No files found in scripts directory.")
        return

    result = subprocess.run(["chmod", "+x"] + script_paths, capture_output=True)
    if result.returncode == 0:
        ok(f"chmod +x applied to all files in {scripts_dir}")
    else:
        warn(f"chmod failed: {result.stderr.decode().strip()}")


# ── phase 6: seed static data ─────────────────────────────────────────────────


def _check_mongodb_running() -> bool:
    """Return True if MongoDB is accepting connections."""
    for client in ("mongosh", "mongo"):
        try:
            result = subprocess.run(
                [client, "--eval", "db.runCommand({ping:1})", "--quiet"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False


def _seed_spread_costs():
    step("Seeding spread costs into MongoDB...")
    from sysdata.data_blob import dataBlob
    from sysdata.csv.csv_spread_costs import csvSpreadCostData
    from sysdata.mongodb.mongo_spread_costs import mongoSpreadCostData

    data = dataBlob()
    data_in = csvSpreadCostData()
    data_out = mongoSpreadCostData(data.mongo_db)
    for instrument_code in data_in.get_list_of_instruments():
        spread = data_in.get_spread_cost(instrument_code)
        data_out.update_spread_cost(instrument_code, spread)
    ok("Spread costs seeded")


def _seed_fx_prices():
    step("Seeding spot FX prices into Parquet...")
    from sysdata.csv.csv_spot_fx import csvFxPricesData
    from sysproduction.data.currency_data import dataCurrency

    csv_fx = csvFxPricesData()
    db_fx = dataCurrency().db_fx_prices_data
    for code in csv_fx.get_list_of_fxcodes():
        prices = csv_fx.get_fx_prices(code)
        db_fx.add_fx_prices(code=code, fx_price_data=prices, ignore_duplication=True)
    ok("FX prices seeded")


def _seed_multiple_prices():
    step("Seeding multiple prices into Parquet...")
    from sysdata.csv.csv_multiple_prices import csvFuturesMultiplePricesData
    from sysproduction.data.prices import diagPrices

    db_multiple = diagPrices().db_futures_multiple_prices_data
    csv_multiple = csvFuturesMultiplePricesData()
    for instrument_code in csv_multiple.get_list_of_instruments():
        prices = csv_multiple.get_multiple_prices(instrument_code)
        db_multiple.add_multiple_prices(
            instrument_code, prices, ignore_duplication=True
        )
    ok("Multiple prices seeded")


def _seed_adjusted_prices():
    step("Seeding adjusted prices into Parquet...")
    from syscore.constants import arg_not_supplied
    from sysdata.csv.csv_adjusted_prices import csvFuturesAdjustedPricesData
    from sysproduction.data.prices import diagPrices

    db_adjusted = diagPrices().db_futures_adjusted_prices_data
    csv_adjusted = csvFuturesAdjustedPricesData(arg_not_supplied)
    for instrument_code in csv_adjusted.get_list_of_instruments():
        prices = csv_adjusted.get_adjusted_prices(instrument_code)
        db_adjusted.add_adjusted_prices(
            instrument_code, prices, ignore_duplication=True
        )
    ok("Adjusted prices seeded")


def phase_seed_static_data(config: dict):
    section("STEP 6/7 — Seeding static data from shipped CSVs")
    print(
        "  Copies the data that ships with pysystemtrade (spread costs, FX prices,\n"
        "  multiple prices, adjusted prices) into your MongoDB/Parquet stores.\n"
        "  IB Gateway does NOT need to be running for this step.\n"
        "\n"
        "  Note: shipped CSV data was last updated March 2024. The daily production\n"
        "  processes will keep it current from today onward.\n"
    )

    if not yes_no("Proceed?"):
        warn("Skipping static data seed.")
        return

    if not _check_mongodb_running():
        warn("Cannot reach MongoDB. Start it first, then re-run this script.")
        print(
            f"\n"
            f"    mongod --dbpath {config['mongo_data']} \\\n"
            f"           --fork \\\n"
            f"           --logpath {config['mongo_data']}/mongod.log\n"
        )
        return

    ok("MongoDB is reachable")
    print()

    for seed_fn in (_seed_spread_costs, _seed_fx_prices, _seed_multiple_prices, _seed_adjusted_prices):
        try:
            seed_fn()
        except Exception as exc:
            warn(f"{seed_fn.__name__} failed: {exc}")
            if not yes_no("Continue with remaining steps?"):
                return


# ── phase 7: crontab ──────────────────────────────────────────────────────────


def phase_crontab():
    section("STEP 7/7 — Production crontab")

    crontab_src = PYSYS_CODE / "sysproduction" / "linux" / "crontab"

    print(
        f"  The supplied crontab at:\n"
        f"      {crontab_src}\n"
        f"  schedules all production processes on weekdays (price updates,\n"
        f"  order execution, backups, reports).\n"
    )

    if not yes_no("Install the production crontab now?", default=False):
        warn("Skipping. Install manually when ready:")
        print(f"\n    crontab -e   # paste the contents of {crontab_src}\n")
        return

    crontab_content = crontab_src.read_text()

    existing = subprocess.run(["crontab", "-l"], capture_output=True)
    if existing.returncode == 0 and existing.stdout.strip():
        warn("You already have a crontab:")
        print(existing.stdout.decode())
        if not yes_no("Append pysystemtrade entries to the existing crontab?", default=False):
            warn("Skipping crontab installation.")
            return
        crontab_content = existing.stdout.decode().rstrip() + "\n\n" + crontab_content

    proc = subprocess.run(
        ["crontab", "-"], input=crontab_content.encode(), capture_output=True
    )
    if proc.returncode == 0:
        ok("Crontab installed")
    else:
        warn(f"crontab installation failed: {proc.stderr.decode().strip()}")
        print(f"  Install manually: crontab -e  (paste contents of {crontab_src})")


# ── final checklist ───────────────────────────────────────────────────────────


def print_manual_steps(config: dict):
    section("SETUP COMPLETE — Remaining manual steps")

    scripts = f"{PYSYS_CODE}/sysproduction/linux/scripts"

    print(
        textwrap.dedent(
            f"""\
            The automated steps are done. The following require manual action:

            IB GATEWAY  (required before any live data or trading)
              [ ] Download IB Gateway from interactivebrokers.com
              [ ] Set socket port to 4001
              [ ] Add 127.0.0.1 to the Trusted IPs whitelist
              [ ] Disable "Read-Only API"
              [ ] (Recommended) Install IBC for auto-login:
                      https://github.com/IbcAlpha/IBC

            SHELL  (do this now before continuing)
              [ ] Reload your shell:
                      source ~/.profile

            MONGODB  (if not already running)
              [ ] Start MongoDB:
                      mongod --dbpath {config["mongo_data"]} \\
                             --fork \\
                             --logpath {config["mongo_data"]}/mongod.log

            CONTRACT PRICE DATA  (requires IB Gateway running; takes several hours)
              [ ] Download historical contract prices from IB:
                      python -m sysinit.futures.seed_price_data_from_IB
              [ ] Update the sampled contract list:
                      {scripts}/update_sampled_contracts

            ROLL CALENDARS  (choose one)
              [ ] Fast path (uses shipped CSVs, may miss recent rolls):
                      python -m sysinit.futures.rollcalendars_from_providedcsv_prices
              [ ] Correct path (builds from your IB prices, per instrument):
                      python -m sysinit.futures.build_roll_calendars

            STRATEGY CONFIGURATION
              [ ] Run a backtest and confirm it works:
                      python -c "from systems.provided.futures_chapter15.basesystem \\
                                 import futures_system; s=futures_system(); \\
                                 print(s.portfolio.get_notional_position('GOLD').tail())"
              [ ] Freeze parameters into private/my_production_config.yaml
              [ ] Create private/private_control_config.yaml
              [ ] Add strategy_list + strategy_capital_allocation to private_config.yaml
              (See docs/live_trading_setup.md — Phase 4 for details)

            PRE-LIVE CHECKS
              [ ] Validate data in interactive_diagnostics:
                      {scripts}/interactive_diagnostics
              [ ] Initialise capital:
                      {scripts}/interactive_update_capital_manual
              [ ] Set trade and position limits:
                      {scripts}/interactive_controls
              [ ] Paper trade for at least two weeks before switching to a live account

            TO SWITCH FROM PAPER TO LIVE
              [ ] Change broker_account in private/private_config.yaml
                  from your DU number to your U number
              [ ] Re-initialise capital from the live account value
              [ ] Clear any residual paper orders from the stack

            REFERENCE
              Full setup guide:    docs/live_trading_setup.md
              Deep reference:      docs/production.md
            """
        )
    )


# ── entry point ───────────────────────────────────────────────────────────────


def main():
    print(
        textwrap.dedent(
            """\

            ================================================================
              pysystemtrade -- Live Trading Setup
            ================================================================

            This script automates the mechanical parts of getting
            pysystemtrade configured for live trading with Interactive
            Brokers.

            It will NOT:
              - configure IB Gateway (requires the GUI)
              - download historical prices from IB (a separate step)
              - make trading decisions for you

            Press Ctrl-C at any time to abort.
            """
        )
    )

    if not yes_no("Continue?"):
        sys.exit(0)

    try:
        config = phase_config()
        phase_directories(config)
        phase_env_vars(config)
        phase_private_config(config)
        phase_make_scripts_executable()
        phase_seed_static_data(config)
        phase_crontab()
        print_manual_steps(config)
    except KeyboardInterrupt:
        print("\n\n  Aborted.")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Master launcher for the IQM Bitfinex lending bot.
Step A: Bootstrap historical data and baselines if data/historical/tBTCUSD_1m.csv is missing.
Step B: Confirm baselines are set, then Step C: start the live IQM engine (run_iqm).
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent
BTC_CSV = PROJECT_ROOT / "data" / "historical" / "tBTCUSD_1m.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def bootstrap_if_needed() -> None:
    """Run data_pipeline download and analysis if tBTCUSD CSV is missing."""
    if BTC_CSV.exists():
        return
    logger.info("Bootstrapping Data...")
    from scripts.data_pipeline import run_pipeline
    run_pipeline()


def _use_advanced_quant_mode() -> None:
    """
    Advanced Quant Mode: no cloud AI dependency.
    Regenerates local pandas-based baselines/reports.
    """
    os.environ["IQM_REPORT_MODE"] = "advanced_quant"
    logger.info("Running in Advanced Quant Mode (local pandas strategy reports).")
    from scripts.data_pipeline import calculate_baselines
    calculate_baselines()


def _google_ai_available() -> bool:
    """
    Global AI health check:
    - missing GOOGLE_API_KEY => fallback
    - explicit 403 from Google => fallback
    """
    key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key:
        logger.warning("GOOGLE_API_KEY missing. Falling back to Advanced Quant Mode.")
        return False
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    try:
        resp = requests.get(url, params={"key": key}, timeout=8)
        if resp.status_code == 403:
            logger.warning("GOOGLE_API_KEY rejected with 403. Falling back to Advanced Quant Mode.")
            return False
        if resp.status_code >= 400:
            logger.warning("Google AI check returned %s. Falling back to Advanced Quant Mode.", resp.status_code)
            return False
        return True
    except Exception as e:
        logger.warning("Google AI check failed (%s). Falling back to Advanced Quant Mode.", e)
        return False


def main() -> None:
    bootstrap_if_needed()
    if not _google_ai_available():
        _use_advanced_quant_mode()
    else:
        os.environ["IQM_REPORT_MODE"] = "ai_enabled"
        logger.info("Google AI key available. Using AI-augmented mode.")
    logger.info("Baselines Set. Igniting IQM Engine...")
    from run_iqm import main as iqm_main
    try:
        asyncio.run(iqm_main())
    except KeyboardInterrupt:
        logger.info("IQM interrupted.")


if __name__ == "__main__":
    main()

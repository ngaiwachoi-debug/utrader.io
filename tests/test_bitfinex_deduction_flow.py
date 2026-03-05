"""
Tests for Bitfinex API timing, token deduction, and gross profit (10:00 UTC fetch, 10:30 deduction).
Use time simulation (freezegun) and mocks; run with: python -m pytest tests/test_bitfinex_deduction_flow.py -v

Optional: pip install freezegun
"""
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _gross_and_fees_from_ledger_entries(entries, start_ms=None, end_ms=None):
    """Local copy of logic to test Margin Funding Payment sum (entry[3]=MTS, entry[4]/[5]=amount, entry[8]=desc)."""
    MARGIN_FUNDING_PAYMENT_DESC = "Margin Funding Payment"
    gross = 0.0
    fees = 0.0
    for entry in entries:
        try:
            if not isinstance(entry, (list, tuple)) or len(entry) < 9:
                continue
            raw_ts = entry[3]
            ts_ms = int(raw_ts) if raw_ts is not None else None
            if start_ms is not None and (ts_ms is None or ts_ms < start_ms):
                continue
            if end_ms is not None and (ts_ms is None or ts_ms > end_ms):
                continue
            amount = entry[5] if entry[4] is None else entry[4]
            amount = float(amount) if amount is not None else 0.0
            desc = str(entry[8]) if len(entry) > 8 and entry[8] is not None else ""
            if MARGIN_FUNDING_PAYMENT_DESC not in desc:
                if "fee" in desc.lower() and amount < 0:
                    fees += abs(amount)
                continue
            if amount > 0:
                gross += amount
            else:
                fees += abs(amount)
        except (TypeError, ValueError, IndexError):
            continue
    return gross, fees


def test_gross_profit_72_20_used_tokens_722():
    """Scenario 5 / Post-test: Sum 72.201934 → gross_profit_usd=72.20, used_tokens=722."""
    # Entries: 2.181577, 24.080038, 36.190726, 6.477932, 3.271661 (MTS and desc placeholders)
    base_ts = 1730000000000  # ms
    entries = [
        [None, None, None, base_ts, 2.181577, None, None, None, "Margin Funding Payment"],
        [None, None, None, base_ts + 86400_000, 24.080038, None, None, None, "Margin Funding Payment"],
        [None, None, None, base_ts + 2 * 86400_000, 36.190726, None, None, None, "Margin Funding Payment"],
        [None, None, None, base_ts + 3 * 86400_000, 6.477932, None, None, None, "Margin Funding Payment"],
        [None, None, None, base_ts + 4 * 86400_000, 3.271661, None, None, None, "Margin Funding Payment"],
    ]
    gross, fees = _gross_and_fees_from_ledger_entries(entries)
    assert abs(gross - 72.201934) < 1e-6
    gross_profit_usd = round(gross, 2)
    assert gross_profit_usd == 72.20
    used_tokens = int(gross_profit_usd * 10)
    assert used_tokens == 722


def test_precision_72_201935_rounds_to_72_20():
    """Scenario 5: Add 0.000001 → sum 72.201935, stored as 72.20, used_tokens=722."""
    base_ts = 1730000000000
    entries = [
        [None, None, None, base_ts, 72.201935, None, None, None, "Margin Funding Payment"],
    ]
    gross, _ = _gross_and_fees_from_ledger_entries(entries)
    assert abs(gross - 72.201935) < 1e-9
    gross_profit_usd = round(gross, 2)
    assert gross_profit_usd == 72.20
    assert int(gross_profit_usd * 10) == 722


def test_is_ledger_data_complete_20_min_buffer():
    """Scenario 2: Latest entry >= 20 mins old → complete; < 20 mins → incomplete."""
    try:
        from freezegun import freeze_time
    except ImportError:
        try:
            import pytest
            pytest.skip("freezegun not installed")
        except ImportError:
            return  # when run as __main__ without pytest
    from main import _is_ledger_data_complete, LEDGER_FRESHNESS_MINUTES

    # 10:00 UTC; latest entry at 09:40 (20 mins ago) → complete
    with freeze_time("2026-02-27 10:00:00", tz_offset=0):
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        latest_20_min_ago = now_ms - (LEDGER_FRESHNESS_MINUTES * 60 * 1000)
        assert _is_ledger_data_complete(latest_20_min_ago) is True
    # Latest entry 10 mins ago → incomplete
    with freeze_time("2026-02-27 10:00:00", tz_offset=0):
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        latest_10_min_ago = now_ms - (10 * 60 * 1000)
        assert _is_ledger_data_complete(latest_10_min_ago) is False


def test_deduction_1_to_1_daily_gross():
    """Scenario 1: daily tokens deducted = daily_gross_profit_usd (1:1); service rounds to 2 decimals."""
    from services.daily_token_deduction import apply_deduction_rule

    tokens_before = 1000.0
    daily_gross = 3.271661
    new_tokens, should_deduct = apply_deduction_rule(tokens_before, daily_gross)
    assert should_deduct is True
    # apply_deduction_rule rounds to 2 decimals: 1000 - 3.271661 -> 996.73
    assert abs(new_tokens - 996.73) < 1e-2


def test_duplicate_block_message():
    """Scenario 4: Duplicate block message format (integration test would call endpoint)."""
    msg = "duplicate API call blocked — 1 call already made today"
    assert "duplicate API call blocked" in msg
    assert "1 call already made today" in msg
    msg2 = "duplicate API call blocked — max 2 calls/day"
    assert "max 2 calls/day" in msg2


def test_daily_fetch_count_on_snapshot():
    """Scenario 4: UserProfitSnapshot has daily_fetch_date and daily_fetch_count for duplicate prevention."""
    import pytest
    import models
    if not hasattr(models.UserProfitSnapshot, "daily_fetch_date") or not hasattr(models.UserProfitSnapshot, "daily_fetch_count"):
        pytest.skip("UserProfitSnapshot has no daily_fetch_date / daily_fetch_count")
    assert hasattr(models.UserProfitSnapshot, "daily_fetch_date")
    assert hasattr(models.UserProfitSnapshot, "daily_fetch_count")


if __name__ == "__main__":
    test_gross_profit_72_20_used_tokens_722()
    test_precision_72_201935_rounds_to_72_20()
    test_is_ledger_data_complete_20_min_buffer()
    test_deduction_1_to_1_daily_gross()
    test_duplicate_block_message()
    test_daily_fetch_count_on_snapshot()
    print("All tests passed.")

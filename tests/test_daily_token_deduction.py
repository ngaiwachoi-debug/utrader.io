"""
Unit tests for daily token deduction (10:30 UTC; uses snapshot from 10:00 UTC API fetch).

Run from project root:
  python -m pytest tests/test_daily_token_deduction.py -v
  or: python tests/test_daily_token_deduction.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_deduction_case_1_tokens_2000_profit_500():
    """Case 1: tokens_remaining=2000, profit=500 → tokens_remaining=1500."""
    from services.daily_token_deduction import apply_deduction_rule

    new_tokens, should_deduct = apply_deduction_rule(2000.0, 500.0)
    assert should_deduct is True
    assert new_tokens == 1500.0


def test_deduction_case_2_tokens_100_profit_200():
    """Case 2: tokens_remaining=100, profit=200 → tokens_remaining=0."""
    from services.daily_token_deduction import apply_deduction_rule

    new_tokens, should_deduct = apply_deduction_rule(100.0, 200.0)
    assert should_deduct is True
    assert new_tokens == 0.0


def test_deduction_case_3_negative_profit_unchanged():
    """Case 3: profit=-50 → tokens_remaining unchanged (no deduction)."""
    from services.daily_token_deduction import apply_deduction_rule

    tokens_before = 1000.0
    new_tokens, should_deduct = apply_deduction_rule(tokens_before, -50.0)
    assert should_deduct is False
    assert new_tokens == tokens_before


def test_deduction_zero_profit_unchanged():
    """Zero profit: do not deduct."""
    from services.daily_token_deduction import apply_deduction_rule

    tokens_before = 500.0
    new_tokens, should_deduct = apply_deduction_rule(tokens_before, 0.0)
    assert should_deduct is False
    assert new_tokens == tokens_before


if __name__ == "__main__":
    test_deduction_case_1_tokens_2000_profit_500()
    test_deduction_case_2_tokens_100_profit_200()
    test_deduction_case_3_negative_profit_unchanged()
    test_deduction_zero_profit_unchanged()
    print("All tests passed.")

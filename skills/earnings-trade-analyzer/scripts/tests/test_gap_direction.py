"""Gap direction fix: a gap DOWN must never produce a buy-grade."""

from datetime import date, timedelta

from analyze_earnings_trades import analyze_stock
from scorer import calculate_composite_score


def test_gap_down_with_perfect_factors_is_capped_at_d():
    r = calculate_composite_score(100, 100, 100, 100, 100, gap_direction="down")
    assert r["grade"] == "D"
    assert r["component_breakdown"]["Gap Size"]["score"] == 0.0
    assert r["gap_direction"] == "down"
    assert "not" in r["guidance"].lower()


def test_gap_up_unchanged():
    r = calculate_composite_score(100, 100, 100, 100, 100, gap_direction="up")
    assert r["grade"] == "A"
    assert r["composite_score"] == 100.0


def test_default_direction_is_up_for_backward_compatibility():
    assert calculate_composite_score(100, 100, 100, 100, 100)["grade"] == "A"


def _prices(gap_factor):
    """250 sessions with a strong uptrend (+0.8%/day), then an earnings gap (most-recent-first).

    With a 0.88 gap the upstream scorer returned 86.0 / grade A for this series.
    """
    rows = []
    d = date(2026, 1, 2)
    price = 50.0
    for i in range(250):
        price *= 1.008
        rows.append({"date": d.isoformat(), "open": price, "high": price * 1.01,
                     "low": price * 0.99, "close": price, "volume": 1_000_000})
        d += timedelta(days=1)
    earnings = rows[-3]["date"]
    rows[-2]["open"] = rows[-3]["close"] * gap_factor
    rows[-2]["close"] = rows[-2]["open"]
    rows[-1]["open"] = rows[-1]["close"] = rows[-2]["close"]
    return list(reversed(rows)), earnings


def test_end_to_end_crash_after_strong_run_is_not_grade_a():
    prices, earnings = _prices(0.88)  # -12% gap after a strong uptrend
    out = analyze_stock(prices, earnings, "amc")
    assert out["gap"]["gap_type"] == "down"
    assert out["composite"]["grade"] == "D"


def test_end_to_end_gap_up_still_scores_high():
    prices, earnings = _prices(1.12)
    out = analyze_stock(prices, earnings, "amc")
    assert out["gap"]["gap_type"] == "up"
    assert out["composite"]["grade"] in ("A", "B")

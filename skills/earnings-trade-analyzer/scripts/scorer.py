#!/usr/bin/env python3
"""
Composite Scorer for Earnings Trade Analyzer

Combines 5 factor scores with fixed weights into a composite score (0-100)
and assigns letter grades (A/B/C/D).

Component Weights:
  gap_size:            25%
  pre_earnings_trend:  30%
  volume_trend:        20%
  ma200_position:      15%
  ma50_position:       10%

Grade Thresholds:
  A: 85+   "Strong earnings reaction with institutional accumulation"
  B: 70-84 "Good earnings reaction worth monitoring"
  C: 55-69 "Mixed signals, use caution"
  D: <55   "Weak setup, avoid"

Direction rule (fix): the scorer rates LONG setups only. A gap DOWN is not
a long setup, so it gets a gap score of 0 and the grade is capped at D,
whatever the other factors say. (Upstream scored |gap|, so a -10% crash
could reach grade A with "consider entry" guidance.)
"""

COMPONENT_WEIGHTS = {
    "gap_size": 0.25,
    "pre_earnings_trend": 0.30,
    "volume_trend": 0.20,
    "ma200_position": 0.15,
    "ma50_position": 0.10,
}

GRADE_THRESHOLDS = [
    (85, "A", "Strong earnings reaction with institutional accumulation"),
    (70, "B", "Good earnings reaction worth monitoring"),
    (55, "C", "Mixed signals, use caution"),
    (0, "D", "Weak setup, avoid"),
]

GRADE_GUIDANCE = {
    "A": "Strong upward reaction. Candidate for further analysis (pullback to gap support or continuation); not a buy signal by itself.",
    "B": "Monitor for follow-through buying. Wait for pullback to key support or volume confirmation.",
    "C": "Additional analysis needed. Consider waiting for clearer price action or catalyst.",
    "D": "Avoid trading. Weak setup with poor risk/reward profile.",
}


GAP_DOWN_GUIDANCE = (
    "Gap down after earnings: this scorer rates long setups only. "
    "Do not treat this as a buy signal."
)


def calculate_composite_score(
    gap_score: float,
    trend_score: float,
    volume_score: float,
    ma200_score: float,
    ma50_score: float,
    gap_direction: str = "up",
) -> dict:
    """
    Calculate weighted composite score and assign grade.

    Args:
        gap_score: Gap size score (0-100)
        trend_score: Pre-earnings trend score (0-100)
        volume_score: Volume trend score (0-100)
        ma200_score: MA200 position score (0-100)
        ma50_score: MA50 position score (0-100)
        gap_direction: 'up' or 'down'. 'down' forces gap score 0 and grade D.

    Returns:
        dict with:
          - composite_score: float (0-100)
          - grade: str ('A', 'B', 'C', or 'D')
          - grade_description: str
          - guidance: str
          - weakest_component: str
          - weakest_score: float
          - strongest_component: str
          - strongest_score: float
          - component_breakdown: dict
    """
    gap_down = str(gap_direction).lower() == "down"
    if gap_down:
        gap_score = 0.0

    components = {
        "Gap Size": {"score": gap_score, "weight": COMPONENT_WEIGHTS["gap_size"]},
        "Pre-Earnings Trend": {
            "score": trend_score,
            "weight": COMPONENT_WEIGHTS["pre_earnings_trend"],
        },
        "Volume Trend": {"score": volume_score, "weight": COMPONENT_WEIGHTS["volume_trend"]},
        "MA200 Position": {"score": ma200_score, "weight": COMPONENT_WEIGHTS["ma200_position"]},
        "MA50 Position": {"score": ma50_score, "weight": COMPONENT_WEIGHTS["ma50_position"]},
    }

    composite_score = sum(comp["score"] * comp["weight"] for comp in components.values())
    composite_score = round(composite_score, 1)

    # Determine grade
    grade = "D"
    grade_description = "Weak setup, avoid"
    for threshold, g, desc in GRADE_THRESHOLDS:
        if composite_score >= threshold:
            grade = g
            grade_description = desc
            break

    guidance = GRADE_GUIDANCE.get(grade, "")

    if gap_down:
        grade = "D"
        grade_description = "Gap down: not a long setup"
        guidance = GAP_DOWN_GUIDANCE

    # Find weakest and strongest components
    weakest_name = min(components, key=lambda k: components[k]["score"])
    strongest_name = max(components, key=lambda k: components[k]["score"])

    component_breakdown = {
        name: {
            "score": comp["score"],
            "weight": comp["weight"],
            "weighted_score": round(comp["score"] * comp["weight"], 1),
        }
        for name, comp in components.items()
    }

    return {
        "composite_score": composite_score,
        "grade": grade,
        "grade_description": grade_description,
        "guidance": guidance,
        "weakest_component": weakest_name,
        "weakest_score": components[weakest_name]["score"],
        "strongest_component": strongest_name,
        "strongest_score": components[strongest_name]["score"],
        "component_breakdown": component_breakdown,
        "gap_direction": "down" if gap_down else "up",
    }

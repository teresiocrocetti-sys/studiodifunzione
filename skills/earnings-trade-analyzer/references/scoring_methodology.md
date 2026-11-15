# Earnings Trade Analyzer - Scoring Methodology

## Overview

The Earnings Trade Analyzer uses a 5-factor weighted scoring system to evaluate post-earnings stock setups. Each stock receives a composite score (0-100) and a letter grade (A/B/C/D).

## 5-Factor Scoring System

### Factor 1: Gap Size (25% Weight)

Measures the magnitude of the earnings gap, regardless of direction. Larger gaps indicate stronger institutional conviction.

| Absolute Gap | Score |
|-------------|-------|
| >= 10%      | 100   |
| >= 7%       | 85    |
| >= 5%       | 70    |
| >= 3%       | 55    |
| >= 1%       | 35    |
| < 1%        | 15    |

**Timing Logic:**
- **BMO (Before Market Open):** gap = open[earnings_date] / close[previous_day] - 1
- **AMC (After Market Close):** gap = open[next_day] / close[earnings_date] - 1
- **Unknown:** Uses AMC logic as default

### Factor 2: Pre-Earnings Trend (30% Weight)

Measures the 20-day price return leading into earnings. Stocks trending up before a positive earnings gap show stronger momentum characteristics.

| 20-Day Return | Score |
|--------------|-------|
| >= 15%       | 100   |
| >= 10%       | 85    |
| >= 5%        | 70    |
| >= 0%        | 50    |
| >= -5%       | 30    |
| < -5%        | 15    |

### Factor 3: Volume Trend (20% Weight)

Ratio of 20-day average volume to 60-day average volume around the earnings date. Higher ratios indicate increased institutional interest and accumulation.

| Volume Ratio (20d/60d) | Score |
|------------------------|-------|
| >= 2.0x                | 100   |
| >= 1.5x                | 80    |
| >= 1.2x                | 60    |
| >= 1.0x                | 40    |
| < 1.0x                 | 20    |

### Factor 4: MA200 Position (15% Weight)

Current price position relative to the 200-day Simple Moving Average. Stocks above their 200-day SMA are in long-term uptrends.

| Distance from MA200 | Score |
|---------------------|-------|
| >= 20%              | 100   |
| >= 10%              | 85    |
| >= 5%               | 70    |
| >= 0%               | 55    |
| >= -5%              | 35    |
| < -5%               | 15    |

### Factor 5: MA50 Position (10% Weight)

Current price position relative to the 50-day Simple Moving Average. Stocks above their 50-day SMA show medium-term strength.

| Distance from MA50 | Score |
|--------------------|-------|
| >= 10%             | 100   |
| >= 5%              | 80    |
| >= 0%              | 60    |
| >= -5%             | 35    |
| < -5%              | 15    |

## Grade Thresholds

| Grade | Score Range | Description |
|-------|-----------|-------------|
| A     | 85-100    | Strong earnings reaction with institutional accumulation |
| B     | 70-84     | Good earnings reaction worth monitoring |
| C     | 55-69     | Mixed signals, use caution |
| D     | 0-54      | Weak setup, avoid |

## Entry Quality Filter

When `--apply-entry-filter` is enabled, the following stocks are excluded (this is what the code does;
the upstream documentation said "< $10", which did not match the code):
- Stocks with current price < $30
- Stocks with |gap| >= 10% AND composite score >= 85

The code cites a "517-trade backtest" for these two rules (win rate 40.6% for $10-$30, 33.3% for the
high-gap/high-score group, vs 54.5% baseline). The backtest data and script are **not published** in the
upstream repository, so these figures cannot be verified. Note that, if accurate, they mean the highest
grades with the largest gaps performed *worse* than average.

## Direction rule (fix in this copy)

The scorer rates **long** setups only. A gap **down** gets a gap score of 0 and the grade is capped at D.
Upstream scored the absolute gap, so a stock up ~17% in 20 days that then gapped down 12% scored
86.0 / grade A with "consider entry" guidance (reproduced in `scripts/tests/test_gap_direction.py`).

## Evidence status

Weights (25/30/20/15/10) and thresholds are design choices of the upstream author. No published,
reproducible validation supports the claim that higher grades lead to stronger post-earnings drift.
Treat grades as a screening aid, not as trading signals.

## Composite Score Formula

```
composite_score = (gap_score * 0.25) + (trend_score * 0.30) + (volume_score * 0.20)
                + (ma200_score * 0.15) + (ma50_score * 0.10)
```

The weights sum to exactly 1.0 (100%).

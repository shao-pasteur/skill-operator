#!/usr/bin/env python3
"""
bollinger.py — compute Bollinger Bands and where the current price sits in them

Usage:
    Pass a JSON file (or JSON on stdin) in this format:
    {
      "symbol": "2330",
      "name": "TSMC",
      "closes": [880, 885, 878, ...],   // at least 20 trading days of closes, oldest first
      "current_price": 892.0             // latest trade price (for intraday snapshots); defaults to the last close
    }

    python3 bollinger.py --input stock.json
    cat stock.json | python3 bollinger.py

    Several stocks at once are supported too: pass a list of such objects and the output is a list.

Output (JSON, printed to stdout):
    {
      "symbol": "2330",
      "name": "TSMC",
      "period": 20,
      "sma": 883.4,
      "upper_band": 901.2,
      "lower_band": 865.6,
      "std_dev": 8.9,
      "current_price": 892.0,
      "position": "within",   // below_lower / near_lower / within / near_upper / above_upper
      "pct_b": 0.62            // %B: (price - lower) / (upper - lower); 0–1 inside the band, <0 below the lower band, >1 above the upper band
    }

How the position is decided:
    - below_lower : price < lower band
    - near_lower  : lower band <= price < lower band + (band width * NEAR_BAND_THRESHOLD)
    - near_upper  : upper band - (band width * NEAR_BAND_THRESHOLD) < price <= upper band
    - above_upper : price > upper band
    - within      : anything else (middle of the band)

This is only an objective calculation; how to read it and whether to act on it is the user's own judgment.
The script never outputs buy/sell advice, and report generation follows the same rule.
"""

import argparse
import json
import statistics
import sys

PERIOD = 20
NUM_STD = 2
NEAR_BAND_THRESHOLD = 0.15  # within 15% of the band width counts as near the upper or lower band


def compute_bollinger(closes, current_price=None, period=PERIOD, num_std=NUM_STD):
    if len(closes) < period:
        raise ValueError(
            f"only {len(closes)} closing prices; Bollinger Bands need at least {period}"
        )

    window = closes[-period:]
    sma = statistics.fmean(window)
    std = statistics.pstdev(window)
    upper = sma + num_std * std
    lower = sma - num_std * std

    if current_price is None:
        current_price = closes[-1]

    band_width = upper - lower
    if band_width == 0:
        pct_b = 0.5
    else:
        pct_b = (current_price - lower) / band_width

    if current_price < lower:
        position = "below_lower"
    elif current_price > upper:
        position = "above_upper"
    elif band_width > 0 and current_price < lower + band_width * NEAR_BAND_THRESHOLD:
        position = "near_lower"
    elif band_width > 0 and current_price > upper - band_width * NEAR_BAND_THRESHOLD:
        position = "near_upper"
    else:
        position = "within"

    return {
        "period": period,
        "sma": round(sma, 2),
        "upper_band": round(upper, 2),
        "lower_band": round(lower, 2),
        "std_dev": round(std, 2),
        "current_price": round(current_price, 2),
        "position": position,
        "pct_b": round(pct_b, 3),
    }


def process_one(item):
    result = compute_bollinger(
        closes=item["closes"],
        current_price=item.get("current_price"),
    )
    result["symbol"] = item.get("symbol")
    result["name"] = item.get("name")
    return result


def main():
    parser = argparse.ArgumentParser(description="Compute Bollinger Bands and where the current price sits in them")
    parser.add_argument("--input", "-i", help="input JSON file; reads stdin when omitted")
    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    if isinstance(data, list):
        output = [process_one(item) for item in data]
    else:
        output = process_one(data)

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

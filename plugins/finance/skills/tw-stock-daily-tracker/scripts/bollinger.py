#!/usr/bin/env python3
"""
bollinger.py — 計算布林通道（Bollinger Bands）與目前價格的相對位置

用法：
    輸入一個 JSON 檔案（或從 stdin 讀 JSON），格式：
    {
      "symbol": "2330",
      "name": "台積電",
      "closes": [880, 885, 878, ...],   // 至少 20 個交易日的收盤價，由舊到新排序
      "current_price": 892.0             // 目前最新成交價（盤中快照用），可省略則用 closes 最後一筆
    }

    python3 bollinger.py --input stock.json
    cat stock.json | python3 bollinger.py

    也支援一次算多檔，輸入改成 list of 上面那種物件即可，輸出也會是 list。

輸出（JSON，印到 stdout）：
    {
      "symbol": "2330",
      "name": "台積電",
      "period": 20,
      "sma": 883.4,
      "upper_band": 901.2,
      "lower_band": 865.6,
      "std_dev": 8.9,
      "current_price": 892.0,
      "position": "within",   // below_lower / near_lower / within / near_upper / above_upper
      "pct_b": 0.62            // %B 指標：(price - lower) / (upper - lower)，0~1 之間，<0 表示跌破下軌，>1 表示突破上軌
    }

位置狀態（position）判斷規則：
    - below_lower : 現價 < 下軌
    - near_lower  : 下軌 <= 現價 < 下軌 + (通道寬度 * NEAR_BAND_THRESHOLD)
    - near_upper  : 上軌 - (通道寬度 * NEAR_BAND_THRESHOLD) < 現價 <= 上軌
    - above_upper : 現價 > 上軌
    - within      : 其餘情況（通道中段）

這只是客觀的數學計算結果，怎麼解讀、要不要據此做任何決定，都是使用者自己的判斷 —— 這支 script
本身不輸出任何「買/賣」建議文字，report 產生階段也要遵守同樣原則。
"""

import argparse
import json
import statistics
import sys

PERIOD = 20
NUM_STD = 2
NEAR_BAND_THRESHOLD = 0.15  # 通道寬度的 15% 以內算「接近」上下軌


def compute_bollinger(closes, current_price=None, period=PERIOD, num_std=NUM_STD):
    if len(closes) < period:
        raise ValueError(
            f"收盤價資料只有 {len(closes)} 筆，至少需要 {period} 筆才能計算布林通道"
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
    parser = argparse.ArgumentParser(description="計算布林通道與目前價格相對位置")
    parser.add_argument("--input", "-i", help="輸入 JSON 檔案路徑，不給則從 stdin 讀")
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

import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API_BASE = "https://openapi.sosovalue.com/openapi/v1"
OUTPUT_FILE = "etf_data.json"

SYMBOL = "XRP"
COUNTRY_CODE = "US"
LIMIT = 30


def fetch_json(url, api_key):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "xrp-etf-data/1.0",
            "Accept": "application/json",
            "x-soso-api-key": api_key,
        },
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get_xrp_etf_history():
    api_key = os.environ.get("SOSOVALUE_API_KEY")

    if not api_key:
        raise RuntimeError(
            "SOSOVALUE_API_KEY が設定されていません"
        )

    params = urllib.parse.urlencode(
        {
            "symbol": SYMBOL,
            "country_code": COUNTRY_CODE,
            "limit": LIMIT,
        }
    )

    url = f"{API_BASE}/etfs/summary-history?{params}"

    data = fetch_json(url, api_key)

    # APIのレスポンスが
    # 直接listの場合と data 配下の場合の両方に対応
    if isinstance(data, dict) and "data" in data:
        rows = data["data"]
    else:
        rows = data

    if not isinstance(rows, list):
        raise RuntimeError(
            f"想定外のAPIレスポンスです: {data}"
        )

    return rows


def to_float(value):
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_summary(rows):
    if not rows:
        raise RuntimeError("ETFデータが0件でした")

    # 公式仕様では最新日が先頭
    latest = rows[0]

    latest_flow = to_float(
        latest.get("total_net_inflow")
    )

    cumulative_flow = to_float(
        latest.get("cum_net_inflow")
    )

    total_assets = to_float(
        latest.get("total_net_assets")
    )

    value_traded = to_float(
        latest.get("total_value_traded")
    )

    # 直近7取引日のフロー
    recent_7 = rows[:7]

    seven_day_flow = sum(
        to_float(row.get("total_net_inflow"))
        for row in recent_7
    )

    avg_7_flow = (
        seven_day_flow / len(recent_7)
        if recent_7
        else 0
    )

    previous_flow = (
        to_float(rows[1].get("total_net_inflow"))
        if len(rows) > 1
        else 0
    )

    flow_change = latest_flow - previous_flow

    if latest_flow > 0:
        flow_direction = "inflow"
    elif latest_flow < 0:
        flow_direction = "outflow"
    else:
        flow_direction = "flat"

    return {
        "symbol": SYMBOL,
        "country": COUNTRY_CODE,
        "date": latest.get("date"),
        "daily_net_inflow_usd": latest_flow,
        "previous_day_net_inflow_usd": previous_flow,
        "daily_flow_change_usd": flow_change,
        "seven_trading_day_net_inflow_usd": seven_day_flow,
        "seven_trading_day_average_usd": avg_7_flow,
        "cumulative_net_inflow_usd": cumulative_flow,
        "total_net_assets_usd": total_assets,
        "total_value_traded_usd": value_traded,
        "flow_direction": flow_direction,
    }


def save_output(rows, summary):
    output = {
        "source": "SoSoValue / SoDEX Market Data API",
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "summary": summary,
        "history": rows,
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return output


def main():
    rows = get_xrp_etf_history()
    summary = build_summary(rows)

    output = save_output(
        rows,
        summary,
    )

    print("XRP ETF data updated")
    print(
        json.dumps(
            output["summary"],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

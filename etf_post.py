import os
import json
import urllib.request

import tweepy
from openai import OpenAI


ETF_FILE = "etf_data.json"
BITBANK_TICKER_URL = "https://public.bitbank.cc/xrp_jpy/ticker"


def load_etf_data():
    with open(ETF_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data["summary"]


def get_xrp_price():
    req = urllib.request.Request(
        BITBANK_TICKER_URL,
        headers={
            "User-Agent": "xrp-etf-post/1.0"
        },
    )

    with urllib.request.urlopen(req, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))

    ticker = data["data"]

    last_price = float(ticker["last"])
    open_price = float(ticker["open"])

    change_pct = (
        (last_price - open_price) / open_price * 100
        if open_price
        else 0
    )

    return {
        "last_price_jpy": last_price,
        "change_24h_pct": change_pct,
    }


def format_usd(value):
    value = float(value)

    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"

    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"

    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}K"

    return f"${value:.0f}"


def generate_analysis(etf, price):
    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"]
    )

    daily_flow = etf["daily_net_inflow_usd"]
    seven_day_flow = etf["seven_trading_day_net_inflow_usd"]
    cumulative = etf["cumulative_net_inflow_usd"]
    aum = etf["total_net_assets_usd"]

    prompt = f"""
あなたはXRP市場を専門に分析する金融市場アカウントの編集者です。

以下のデータだけを使って、日本語のX投稿を1本作成してください。

ETFデータ日付:
{etf["date"]}

XRP ETF 日次純流入:
{format_usd(daily_flow)}

直近7取引日累計:
{format_usd(seven_day_flow)}

累計純流入:
{format_usd(cumulative)}

ETF AUM:
{format_usd(aum)}

XRP/JPY:
{price["last_price_jpy"]:.3f}円

XRP 24時間騰落率:
{price["change_24h_pct"]:+.2f}%

分析ルール:

・ETF流入とXRP価格の方向が一致しているかを見る
・ETF流入なのに価格下落なら、ETF需要が価格下落局面でも維持されている可能性を指摘
・ETF流出なのに価格上昇なら、ETF資金と価格が逆行している点を指摘
・数字を大げさに解釈しない
・「機関投資家が買っている」と断定しない
・ETFフローは需要の一指標として扱う
・280文字以内
・最初に「📊 XRP ETF資金フロー」
・最後に #XRP #XRPETF #仮想通貨
・投資助言はしない
"""

    response = client.responses.create(
        model="gpt-5.6",
        input=prompt,
    )

    return response.output_text.strip()


def post_to_x(text):
    client = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )

    response = client.create_tweet(text=text)

    print("X投稿完了")
    print(response)


def main():
    etf = load_etf_data()
    price = get_xrp_price()

    print("ETF date:", etf["date"])
    print(
        "Daily ETF flow:",
        format_usd(etf["daily_net_inflow_usd"]),
    )
    print(
        "7-day ETF flow:",
        format_usd(
            etf["seven_trading_day_net_inflow_usd"]
        ),
    )
    print(
        "XRP price:",
        f'{price["last_price_jpy"]:.3f}円',
    )
    print(
        "XRP 24h:",
        f'{price["change_24h_pct"]:+.2f}%',
    )

    text = generate_analysis(etf, price)

    print("生成された投稿文:")
    print(text)

    dry_run = os.getenv(
        "ETF_DRY_RUN",
        "true",
    ).lower() == "true"

    if dry_run:
        print("=== DRY RUN：Xには投稿しません ===")
        return

    post_to_x(text)


if __name__ == "__main__":
    main()

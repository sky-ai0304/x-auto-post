import os
import json
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import tweepy
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from openai import OpenAI

# =========================
# Secrets check
# =========================

REQUIRED_SECRETS = [
    "OPENAI_API_KEY",
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
]

missing = [name for name in REQUIRED_SECRETS if not os.getenv(name)]

if missing:
    raise RuntimeError(f"Missing secrets: {', '.join(missing)}")


# =========================
# bitbank public API
# =========================

BITBANK_BASE = "https://public.bitbank.cc"
PAIR = "xrp_jpy"


def get_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "x-auto-post/1.0"}
    )

    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def get_ticker():
    data = get_json(f"{BITBANK_BASE}/{PAIR}/ticker")

    if data.get("success") != 1:
        raise RuntimeError("bitbank ticker API error")

    ticker = data["data"]

    last_price = float(ticker["last"])
    open_price = float(ticker["open"])

    change_pct = (
        ((last_price - open_price) / open_price) * 100
        if open_price else 0
    )

    return {
        "last": last_price,
        "open": open_price,
        "high": float(ticker["high"]),
        "low": float(ticker["low"]),
        "change_pct": change_pct,
    }


def get_hourly_candles(days=3):
    """
    RSI/MACD計算用に直近数日分の1時間足を取得
    """
    jst = ZoneInfo("Asia/Tokyo")
    today = datetime.now(jst).date()

    candles = []

    for offset in range(days - 1, -1, -1):
        target_date = today - timedelta(days=offset)
        date_str = target_date.strftime("%Y%m%d")

        url = (
            f"{BITBANK_BASE}/{PAIR}/candlestick/"
            f"1hour/{date_str}"
        )

        try:
            data = get_json(url)

            if data.get("success") != 1:
                continue

            raw = data["data"]["candlestick"][0]["ohlcv"]

            for candle in raw:
                candles.append(
                    {
                        "open": float(candle[0]),
                        "high": float(candle[1]),
                        "low": float(candle[2]),
                        "close": float(candle[3]),
                        "volume": float(candle[4]),
                        "timestamp": int(candle[5]),
                    }
                )

        except Exception as e:
            print(f"Could not load candle {date_str}: {e}")

    # 時刻順
    candles.sort(key=lambda x: x["timestamp"])

    # 重複排除
    unique = {}
    for candle in candles:
        unique[candle["timestamp"]] = candle

    return list(unique.values())


# =========================
# Technical indicators
# =========================

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]

        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (
            avg_gain * (period - 1) + gains[i]
        ) / period

        avg_loss = (
            avg_loss * (period - 1) + losses[i]
        ) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def ema(values, period):
    if len(values) < period:
        return []

    multiplier = 2 / (period + 1)

    first = sum(values[:period]) / period
    result = [first]

    for value in values[period:]:
        next_value = (
            value - result[-1]
        ) * multiplier + result[-1]

        result.append(next_value)

    return result


def calculate_macd(closes):
    if len(closes) < 35:
        return None, None, None

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)

    # EMA26の開始位置に合わせる
    offset = len(ema12) - len(ema26)
    ema12_aligned = ema12[offset:]

    macd_line = [
        fast - slow
        for fast, slow in zip(ema12_aligned, ema26)
    ]

    signal_line = ema(macd_line, 9)

    if not signal_line:
        return None, None, None

    latest_macd = macd_line[-1]
    latest_signal = signal_line[-1]
    histogram = latest_macd - latest_signal
def make_chart(candles, filename="xrp_chart.png"):
    if len(candles) < 35:
        raise RuntimeError("チャート用ローソク足データが不足しています")

    # 直近72本だけ表示
    data = candles[-72:]

    times = [
        datetime.fromtimestamp(
            c["timestamp"] / 1000,
            tz=ZoneInfo("Asia/Tokyo")
        )
        for c in data
    ]

    opens = [c["open"] for c in data]
    highs = [c["high"] for c in data]
    lows = [c["low"] for c in data]
    closes = [c["close"] for c in data]

    # RSI
    rsi_values = []
    for i in range(len(closes)):
        part = closes[:i + 1]
        if len(part) >= 15:
            rsi_values.append(calculate_rsi(part))
        else:
            rsi_values.append(None)

    # MACD
    macd_values = [None] * len(closes)
    signal_values = [None] * len(closes)
    hist_values = [None] * len(closes)

    for i in range(len(closes)):
        part = closes[:i + 1]
　　　　if len(part) >= 35:
    　　　 macd_result = calculate_macd(part)

            if macd_result is not None:
                m, s, h = macd_result

                if m is not None and s is not None and h is not None:
                    macd_values[i] = m
                    signal_values[i] = s
                    hist_values[i] = h

    fig, (ax1, ax2, ax3) = plt.subplots(
        3,
        1,
        figsize=(12, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1, 1]}
    )

    # -----------------
    # ローソク足
    # -----------------
    width = 0.025

    for t, o, h, l, c in zip(times, opens, highs, lows, closes):
        color = "green" if c >= o else "red"

        ax1.plot(
            [t, t],
            [l, h],
            color=color,
            linewidth=1
        )

        bottom = min(o, c)
        height = abs(c - o)

        if height == 0:
            height = 0.01

        ax1.bar(
            t,
            height,
            bottom=bottom,
            width=width,
            color=color,
            align="center"
        )

    ax1.set_title("XRP/JPY 1H")
    ax1.set_ylabel("JPY")
    ax1.grid(alpha=0.2)

    # -----------------
    # MACD
    # -----------------
    ax2.plot(
        times,
        macd_values,
        label="MACD"
    )

    ax2.plot(
        times,
        signal_values,
        label="Signal"
    )

    hist_clean = [
        v if v is not None else 0
        for v in hist_values
    ]

    ax2.bar(
        times,
        hist_clean,
        width=width,
        alpha=0.5,
        label="Histogram"
    )

    ax2.axhline(
        0,
        linewidth=0.8
    )

    ax2.legend(loc="upper left")
    ax2.grid(alpha=0.2)

    # -----------------
    # RSI
    # -----------------
    ax3.plot(
        times,
        rsi_values,
        label="RSI"
    )

    ax3.axhline(
        70,
        linestyle="--",
        linewidth=0.8
    )

    ax3.axhline(
        30,
        linestyle="--",
        linewidth=0.8
    )

    ax3.set_ylim(0, 100)
    ax3.legend(loc="upper left")
    ax3.grid(alpha=0.2)

    ax3.xaxis.set_major_formatter(
        mdates.DateFormatter(
            "%m/%d %H:%M",
            tz=ZoneInfo("Asia/Tokyo")
        )
    )

    plt.xticks(rotation=30)
    plt.tight_layout()

    plt.savefig(
        filename,
        dpi=150,
        bbox_inches="tight"
    )

    plt.close()

    return filename
    return latest_macd, latest_signal, histogram


def market_judgement(rsi, macd, signal):
    score = 0

    if rsi is not None:
        if 50 <= rsi < 70:
            score += 1
        elif rsi < 40:
            score -= 1
        elif rsi >= 70:
            score -= 0.5

    if macd is not None and signal is not None:
        if macd > signal:
            score += 1
        else:
            score -= 1

    if score >= 1.5:
        return "やや強気"
    elif score <= -1:
        return "やや弱気"

    return "中立"


# =========================
# Get market data
# =========================

ticker = get_ticker()
candles = get_hourly_candles(days=3)

if len(candles) < 35:
    raise RuntimeError(
        f"ローソク足データ不足: {len(candles)}本"
    )
chart_file = make_chart(candles)
closes = [c["close"] for c in candles]

rsi = calculate_rsi(closes)
macd, signal, histogram = calculate_macd(closes)

judgement = market_judgement(
    rsi,
    macd,
    signal
)

market_data = f"""
XRP/JPY市場データ（bitbank）
現在値: {ticker['last']:.3f}円
24時間騰落率: {ticker['change_pct']:+.2f}%
24時間高値: {ticker['high']:.3f}円
24時間安値: {ticker['low']:.3f}円
1時間足 RSI(14): {rsi:.1f}
MACD: {macd:.3f}
Signal: {signal:.3f}
Histogram: {histogram:+.3f}
短期判定: {judgement}
"""


# =========================
# OpenAI
# =========================

openai_client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"]
)

prompt = f"""
以下の最新XRP市場データとWeb検索結果を使って、
X向けの日本語投稿を1つ作成してください。

{market_data}

Webでは直近24時間のXRPに関する重要ニュースを検索してください。

条件:
・まず価格、24時間騰落率、RSI、MACDを簡潔に伝える
・テクニカルから短期の見方を1文入れる
・重要ニュースがあれば1件だけ追加する
・重要ニュースが無い場合は「ニュースなし」と書かず、
  テクニカル分析だけで投稿を完成させる
・価格上昇を煽らない
・投資助言をしない
・事実と推測を区別する
・ニュースの日付を確認する
・220文字以内を目安にする
・ハッシュタグは #XRP を含め最大2個
・記事タイトルの丸写しはしない
・前置きや説明は付けず投稿本文だけ出力する
"""

response = openai_client.responses.create(
    model="gpt-5-mini",
    tools=[{"type": "web_search"}],
    input=prompt,
    store=False,
)

text = response.output_text.strip()

if not text:
    raise RuntimeError(
        "AIが投稿文を生成できませんでした"
    )

# 念のため280文字以内
if len(text) > 280:
    text = text[:277] + "..."

print("===== MARKET DATA =====")
print(market_data)

print("===== GENERATED POST =====")
print(text)


# =========================
# X API
# =========================

x_client = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ[
        "X_ACCESS_TOKEN_SECRET"
    ],
)

auth = tweepy.OAuth1UserHandler(
    os.environ["X_API_KEY"],
    os.environ["X_API_SECRET"],
    os.environ["X_ACCESS_TOKEN"],
    os.environ["X_ACCESS_TOKEN_SECRET"],
)

api = tweepy.API(auth)

media = api.media_upload(filename=chart_file)

# 画像付きで投稿
result = x_client.create_tweet(
    text=text,
    media_ids=[media.media_id]
)
print(
    f"Posted successfully: {result.data}"
)

import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import tweepy
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from openai import OpenAI


BITBANK_BASE = "https://public.bitbank.cc"
PAIR = "xrp_jpy"

STATE_FILE = "xrp_alert_state.json"
CHART_FILE = "xrp_alert_chart.png"

MOVE_THRESHOLD = 3.0
STRONG_MOVE_THRESHOLD = 5.0

NORMAL_INTERVAL_HOURS = 4
STRONG_INTERVAL_HOURS = 2

MIN_PRICE_MOVE_FROM_LAST_POST = 1.0


# =========================
# bitbank
# =========================

def get_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "xrp-alert/2.0"}
    )

    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def get_xrp_price():
    data = get_json(
        f"{BITBANK_BASE}/{PAIR}/ticker"
    )

    ticker = data["data"]

    last_price = float(ticker["last"])
    open_price = float(ticker["open"])

    change_pct = (
        (last_price - open_price)
        / open_price
        * 100
        if open_price
        else 0
    )

    return {
        "last": last_price,
        "open": open_price,
        "high": float(ticker["high"]),
        "low": float(ticker["low"]),
        "change_pct": change_pct,
    }


def get_hourly_candles(days=3):
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
            print(
                f"Could not load candle {date_str}: {e}"
            )

    candles.sort(
        key=lambda x: x["timestamp"]
    )

    unique = {}

    for candle in candles:
        unique[candle["timestamp"]] = candle

    return list(unique.values())


# =========================
# Indicators
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
            avg_gain * (period - 1)
            + gains[i]
        ) / period

        avg_loss = (
            avg_loss * (period - 1)
            + losses[i]
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
            (value - result[-1])
            * multiplier
            + result[-1]
        )

        result.append(next_value)

    return result


def calculate_macd(closes):
    if len(closes) < 35:
        return None, None, None

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)

    offset = len(ema12) - len(ema26)

    ema12_aligned = ema12[offset:]

    macd_line = [
        fast - slow
        for fast, slow
        in zip(ema12_aligned, ema26)
    ]

    signal_line = ema(macd_line, 9)

    if not signal_line:
        return None, None, None

    latest_macd = macd_line[-1]
    latest_signal = signal_line[-1]

    histogram = (
        latest_macd - latest_signal
    )

    return (
        latest_macd,
        latest_signal,
        histogram,
    )


def market_judgement(rsi, macd, signal):
    score = 0

    if rsi is not None:
        if 50 <= rsi < 70:
            score += 1
        elif rsi < 40:
            score -= 1
        elif rsi >= 70:
            score -= 0.5

    if (
        macd is not None
        and signal is not None
    ):
        if macd > signal:
            score += 1
        else:
            score -= 1

    if score >= 1.5:
        return "やや強気"

    if score <= -1:
        return "やや弱気"

    return "中立"


# =========================
# Chart
# =========================

def make_chart(candles):
    if len(candles) < 35:
        raise RuntimeError(
            "チャート用ローソク足が不足しています"
        )

    data = candles[-72:]

    times = [
        datetime.fromtimestamp(
            c["timestamp"] / 1000,
            tz=ZoneInfo("Asia/Tokyo"),
        )
        for c in data
    ]

    opens = [c["open"] for c in data]
    highs = [c["high"] for c in data]
    lows = [c["low"] for c in data]
    closes = [c["close"] for c in data]

    rsi_values = []

    for i in range(len(closes)):
        part = closes[: i + 1]

        if len(part) >= 15:
            rsi_values.append(
                calculate_rsi(part)
            )
        else:
            rsi_values.append(None)

    macd_values = [None] * len(closes)
    signal_values = [None] * len(closes)
    hist_values = [None] * len(closes)

    for i in range(len(closes)):
        part = closes[: i + 1]

        if len(part) >= 35:
            m, s, h = calculate_macd(part)

            macd_values[i] = m
            signal_values[i] = s
            hist_values[i] = h

    fig, (ax1, ax2, ax3) = plt.subplots(
        3,
        1,
        figsize=(12, 8),
        sharex=True,
        gridspec_kw={
            "height_ratios": [3, 1, 1]
        },
    )

    width = 0.025

    for t, o, h, l, c in zip(
        times,
        opens,
        highs,
        lows,
        closes,
    ):
        color = "green" if c >= o else "red"

        ax1.plot(
            [t, t],
            [l, h],
            color=color,
            linewidth=1,
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
            align="center",
        )

    ax1.set_title("XRP/JPY 1H")
    ax1.set_ylabel("JPY")
    ax1.grid(alpha=0.2)

    ax2.plot(
        times,
        macd_values,
        label="MACD",
    )

    ax2.plot(
        times,
        signal_values,
        label="Signal",
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
        label="Histogram",
    )

    ax2.axhline(
        0,
        linewidth=0.8,
    )

    ax2.legend(loc="upper left")
    ax2.grid(alpha=0.2)

    ax3.plot(
        times,
        rsi_values,
        label="RSI",
    )

    ax3.axhline(
        70,
        linestyle="--",
        linewidth=0.8,
    )

    ax3.axhline(
        30,
        linestyle="--",
        linewidth=0.8,
    )

    ax3.set_ylim(0, 100)
    ax3.legend(loc="upper left")
    ax3.grid(alpha=0.2)

    ax3.xaxis.set_major_formatter(
        mdates.DateFormatter(
            "%m/%d %H:%M",
            tz=ZoneInfo("Asia/Tokyo"),
        )
    )

    plt.xticks(rotation=30)
    plt.tight_layout()

    plt.savefig(
        CHART_FILE,
        dpi=150,
        bbox_inches="tight",
    )

    plt.close()

    return CHART_FILE


# =========================
# State
# =========================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "last_posted_at": None,
            "last_posted_price": None,
        }

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)

    except Exception:
        return {
            "last_posted_at": None,
            "last_posted_price": None,
        }


def save_state(price):
    state = {
        "last_posted_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "last_posted_price":
            price,
    }

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )


def hours_since_last_post(state):
    value = state.get("last_posted_at")

    if not value:
        return None

    try:
        last_time = datetime.fromisoformat(
            value
        )

        now = datetime.now(
            timezone.utc
        )

        return (
            now - last_time
        ).total_seconds() / 3600

    except Exception:
        return None


def price_change_from_last_post(
    current_price,
    state,
):
    previous = state.get(
        "last_posted_price"
    )

    if not previous:
        return None

    previous = float(previous)

    if previous == 0:
        return None

    return (
        (current_price - previous)
        / previous
        * 100
    )


def should_post(price, state):
    move = abs(
        price["change_pct"]
    )

    if move < MOVE_THRESHOLD:
        return False, (
            f"24h変動率 "
            f"{price['change_pct']:+.2f}% "
            "→ ±3%未満"
        )

    if move >= STRONG_MOVE_THRESHOLD:
        required_hours = (
            STRONG_INTERVAL_HOURS
        )
    else:
        required_hours = (
            NORMAL_INTERVAL_HOURS
        )

    elapsed = hours_since_last_post(
        state
    )

    if (
        elapsed is not None
        and elapsed < required_hours
    ):
        return False, (
            f"前回投稿から"
            f"{elapsed:.2f}時間。"
            f"最低{required_hours}時間待機"
        )

    price_diff = (
        price_change_from_last_post(
            price["last"],
            state,
        )
    )

    if (
        price_diff is not None
        and abs(price_diff)
        < MIN_PRICE_MOVE_FROM_LAST_POST
    ):
        return False, (
            "前回速報価格から"
            f"{price_diff:+.2f}%のみ"
        )

    return True, (
        "速報条件成立："
        f"24h {price['change_pct']:+.2f}%"
    )


# =========================
# AI analysis
# =========================

def generate_post(
    price,
    rsi,
    macd,
    signal,
    histogram,
    support,
    resistance,
    judgement,
):
    client = OpenAI(
        api_key=os.environ[
            "OPENAI_API_KEY"
        ]
    )

    prompt = f"""
あなたはXRP市場を分析する日本語の速報アカウント編集者です。

以下のデータだけを使って、
X向けの急変速報を1本作成してください。

XRP/JPY:
{price["last"]:.3f}円

24時間騰落率:
{price["change_pct"]:+.2f}%

24時間高値:
{price["high"]:.3f}円

24時間安値:
{price["low"]:.3f}円

1時間足RSI:
{rsi:.1f}

MACD:
{macd:.3f}

Signal:
{signal:.3f}

Histogram:
{histogram:.3f}

直近サポート:
{support:.3f}円

直近レジスタンス:
{resistance:.3f}円

短期判定:
{judgement}

ルール:

・最初に「🚨 XRP急変速報」
・価格と24時間騰落率を必ず記載
・RSIの過熱/売られすぎを説明
・MACDとSignalの関係を説明
・上値抵抗と下値支持を具体的な価格で書く
・今後の上昇/下落シナリオを短く示す
・断定しすぎない
・ニュース原因を推測しない
・投資助言をしない
・220文字程度
・最後に #XRP #仮想通貨
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt,
    )

    return response.output_text.strip()


# =========================
# X
# =========================

def post_to_x(text, chart_file):
    x_client = tweepy.Client(
        consumer_key=os.environ[
            "X_API_KEY"
        ],
        consumer_secret=os.environ[
            "X_API_SECRET"
        ],
        access_token=os.environ[
            "X_ACCESS_TOKEN"
        ],
        access_token_secret=os.environ[
            "X_ACCESS_TOKEN_SECRET"
        ],
    )

    auth = tweepy.OAuth1UserHandler(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ[
            "X_ACCESS_TOKEN_SECRET"
        ],
    )

    api = tweepy.API(auth)

    media = api.media_upload(
        filename=chart_file
    )

    response = x_client.create_tweet(
        text=text,
        media_ids=[media.media_id],
    )

    print("X速報投稿完了")
    print(response)


# =========================
# Main
# =========================

def main():
    price = get_xrp_price()
    state = load_state()

    print(
        "XRP:",
        f'{price["last"]:.3f}円',
    )

    print(
        "24h:",
        f'{price["change_pct"]:+.2f}%',
    )

    can_post, reason = should_post(
        price,
        state,
    )

    print(reason)

    if not can_post:
        return

    candles = get_hourly_candles(
        days=3
    )

    if len(candles) < 35:
        raise RuntimeError(
            "ローソク足データ不足"
        )

    closes = [
        c["close"]
        for c in candles
    ]

    recent = candles[-25:]

    support = min(
        c["low"]
        for c in recent
    )

    resistance = max(
        c["high"]
        for c in recent
    )

    rsi = calculate_rsi(
        closes
    )

    macd, signal, histogram = (
        calculate_macd(
            closes
        )
    )

    judgement = market_judgement(
        rsi,
        macd,
        signal,
    )

    chart_file = make_chart(
        candles
    )

    print(
        "RSI:",
        f"{rsi:.1f}",
    )

    print(
        "MACD:",
        f"{macd:.3f}",
    )

    print(
        "Support:",
        f"{support:.3f}",
    )

    print(
        "Resistance:",
        f"{resistance:.3f}",
    )

    print(
        "Judgement:",
        judgement,
    )

    text = generate_post(
        price,
        rsi,
        macd,
        signal,
        histogram,
        support,
        resistance,
        judgement,
    )

    print("生成された速報文:")
    print(text)

    dry_run = os.getenv(
        "XRP_ALERT_DRY_RUN",
        "true",
    ).lower() == "true"

    if dry_run:
        print(
            "=== DRY RUN："
            "Xには投稿しません ==="
        )
        return

    post_to_x(
        text,
        chart_file,
    )

    save_state(
        price["last"]
    )


if __name__ == "__main__":
    main()

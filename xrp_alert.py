import os
import json
import urllib.request
from datetime import datetime, timezone

import tweepy
from openai import OpenAI


BITBANK_TICKER_URL = "https://public.bitbank.cc/xrp_jpy/ticker"

STATE_FILE = "xrp_alert_state.json"

MOVE_THRESHOLD = 3.0
STRONG_MOVE_THRESHOLD = 5.0

NORMAL_INTERVAL_HOURS = 4
STRONG_INTERVAL_HOURS = 2

MIN_PRICE_MOVE_FROM_LAST_POST = 1.0


def get_xrp_price():
    req = urllib.request.Request(
        BITBANK_TICKER_URL,
        headers={
            "User-Agent": "xrp-alert/1.0"
        },
    )

    with urllib.request.urlopen(
        req,
        timeout=20,
    ) as response:
        data = json.loads(
            response.read().decode("utf-8")
        )

    ticker = data["data"]

    last_price = float(ticker["last"])
    open_price = float(ticker["open"])
    high_price = float(ticker["high"])
    low_price = float(ticker["low"])

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
        "high": high_price,
        "low": low_price,
        "change_pct": change_pct,
    }


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
            datetime.now(timezone.utc).isoformat(),

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
        last_time = datetime.fromisoformat(value)

        now = datetime.now(timezone.utc)

        seconds = (
            now - last_time
        ).total_seconds()

        return seconds / 3600

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
            f"24h変動率 {price['change_pct']:+.2f}% "
            "→ ±3%未満なので投稿しません"
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
            f"前回投稿から {elapsed:.2f}時間。"
            f"最低{required_hours}時間空けます"
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
            "前回速報価格からの変化が"
            f"{price_diff:+.2f}%なので投稿しません"
        )

    return True, (
        f"速報条件成立：24h "
        f"{price['change_pct']:+.2f}%"
    )


def generate_post(price, state):
    client = OpenAI(
        api_key=os.environ[
            "OPENAI_API_KEY"
        ]
    )

    previous_price = state.get(
        "last_posted_price"
    )

    if previous_price:
        previous_text = (
            f"{float(previous_price):.3f}円"
        )
    else:
        previous_text = "なし"

    prompt = f"""
あなたはXRP市場を扱う日本語の速報アカウント編集者です。

以下の市場データだけを使って、
X向けの短い速報投稿を1本作成してください。

現在のXRP/JPY:
{price["last"]:.3f}円

24時間騰落率:
{price["change_pct"]:+.2f}%

24時間高値:
{price["high"]:.3f}円

24時間安値:
{price["low"]:.3f}円

前回速報時価格:
{previous_text}

ルール:

・最初に 🚨 または 📈 📉 を使う
・最初の1行で値動きの大きさを伝える
・価格と24時間騰落率を必ず記載
・上昇なら勢いの強さを簡潔に説明
・下落なら売り圧力の強さを簡潔に説明
・RSIやMACDなど、与えられていない数字は作らない
・ニュースや材料を推測しない
・原因が分からないのに理由を断定しない
・煽りすぎない
・投資助言をしない
・220文字以内
・最後に #XRP #仮想通貨
"""

    response = client.responses.create(
        model="gpt-5.6",
        input=prompt,
    )

    return response.output_text.strip()


def post_to_x(text):
    client = tweepy.Client(
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

    response = client.create_tweet(
        text=text
    )

    print("X速報投稿完了")
    print(response)


def main():
    price = get_xrp_price()
    state = load_state()

    print(
        "XRP:",
        f'{price["last"]:.3f}円'
    )

    print(
        "24h:",
        f'{price["change_pct"]:+.2f}%'
    )

    can_post, reason = should_post(
        price,
        state,
    )

    print(reason)

    if not can_post:
        return

    text = generate_post(
        price,
        state,
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

    post_to_x(text)

    save_state(
        price["last"]
    )


if __name__ == "__main__":
    main()

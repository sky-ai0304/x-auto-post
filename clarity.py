import os
import json
import urllib.parse
import urllib.request

import tweepy
from openai import OpenAI


SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
STATE_FILE = "clarity_state.json"

THRESHOLD_POINTS = 5.0
SEARCH_QUERY = "CLARITY Act 2026"


def get_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "clarity-x-bot/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_json_field(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def find_clarity_market():
    params = urllib.parse.urlencode(
        {
            "q": SEARCH_QUERY,
        }
    )

    data = get_json(f"{SEARCH_URL}?{params}")

    candidates = []

    for event in data.get("events", []):
        event_title = event.get("title", "")

        for market in event.get("markets", []):
            question = market.get("question", "")
            text = f"{event_title} {question}".lower()

            if "clarity" not in text:
                continue

            if "2026" not in text:
                continue

            if market.get("closed") is True:
                continue

            outcomes = parse_json_field(market.get("outcomes", []))
            prices = parse_json_field(market.get("outcomePrices", []))

            if not isinstance(outcomes, list) or not isinstance(prices, list):
                continue

            if len(outcomes) != len(prices):
                continue

            yes_price = None

            for outcome, price in zip(outcomes, prices):
                if str(outcome).strip().lower() == "yes":
                    yes_price = float(price)
                    break

            if yes_price is None:
                continue

            volume = float(market.get("volumeNum") or 0)

            candidates.append(
                {
                    "event_title": event_title,
                    "question": question,
                    "yes_probability": yes_price * 100,
                    "volume": volume,
                    "slug": market.get("slug", ""),
                }
            )

    if not candidates:
        raise RuntimeError("CLARITY Act 2026 のPolymarket市場が見つかりませんでした")

    candidates.sort(key=lambda x: x["volume"], reverse=True)

    return candidates[0]


def load_previous_probability():
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return float(data["yes_probability"])

    except Exception:
        return None


def save_probability(probability):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "yes_probability": probability,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def generate_post(current, previous):
    diff = current["yes_probability"] - previous
    direction = "上昇" if diff > 0 else "低下"

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"]
    )

    prompt = f"""
あなたは暗号資産・米国政策を扱うX速報アカウントの編集者です。

まずWeb検索を使って、直近48時間のCLARITY Act関連ニュースを確認してください。

特に以下を優先してください。
・米上院の採決日程
・60票確保の見通し
・民主党/共和党の合意や対立
・修正案
・ステーブルコイン報酬問題
・倫理規定
・ホワイトハウスの発言
・SEC/CFTCの規制方針
・Reuters、Bloomberg、Politico、議会公式、SEC、CFTC、White Houseなど信頼性の高い情報源

Polymarket市場:
2026年中にCLARITY Actが成立・大統領署名されるか

現在のYES確率:
{current["yes_probability"]:.1f}%

前回:
{previous:.1f}%

変化:
{diff:+.1f}ポイント

方向:
{direction}

市場タイトル:
{current["question"]}

検索結果から、今回の確率変動を説明できる明確な新材料が確認できた場合だけ、その理由を投稿文に含めてください。

理由が確認できない場合は、推測せず
「現時点で確率変動の明確な要因は確認できていません」
という趣旨にしてください。

X投稿ルール:
・日本語
・280文字以内
・最初の1行で確率変動を目立たせる
・Polymarketの市場予想であり成立を保証する数字ではないと分かる表現
・煽りすぎない
・事実と推測を混同しない
・XRPへの意味を最後に1文だけ入れる
・URLは入れない
・投資助言はしない
・最後に #CLARITYAct #XRP #仮想通貨
"""

    response = client.responses.create(
        model="gpt-5.6",
        tools=[
            {
                "type": "web_search"
            }
        ],
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
    current = find_clarity_market()

    current_probability = current["yes_probability"]

    print("対象市場:", current["question"])
    print(f"現在YES確率: {current_probability:.1f}%")

    previous = load_previous_probability()

    if previous is None:
        print("初回実行です。基準値だけ保存して投稿しません。")
        save_probability(current_probability)
        return

    diff = current_probability - previous

    print(f"前回: {previous:.1f}%")
    print(f"変化: {diff:+.1f}ポイント")

    if abs(diff) < THRESHOLD_POINTS:
        print(
            f"{THRESHOLD_POINTS:.1f}ポイント未満の変動なので投稿しません。"
        )

        save_probability(current_probability)
        return

    text = generate_post(current, previous)

    print("生成された投稿文:")
    print(text)

    post_to_x(text)

    save_probability(current_probability)


if __name__ == "__main__":
    main()

import os

import tweepy
from openai import OpenAI


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


openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

prompt = """
現在の最新情報をWeb検索し、XRPに関する重要なニュースを1件選んで、
日本語のX投稿を作成してください。

条件：
・できるだけ直近24時間のニュースを優先する
・信頼できる一次情報または大手報道を優先する
・事実と推測を区別する
・価格上昇を煽らない
・投資助言をしない
・ニュースの日付を確認する
・220文字以内
・ハッシュタグは #XRP を含めて最大2個
・記事タイトルの丸写しはしない
・前置きや説明は付けず、投稿本文だけを出力する
・重要な新情報が見つからない場合は、その旨を自然に投稿する
"""

response = openai_client.responses.create(
    model="gpt-5-mini",
    tools=[{"type": "web_search"}],
    input=prompt,
    store=False,
)

text = response.output_text.strip()

if not text:
    raise RuntimeError("AIが投稿文を生成できませんでした")

if len(text) > 280:
    text = text[:277] + "..."

print(f"Generated post: {text}")


x_client = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
)

result = x_client.create_tweet(text=text)

print(f"Posted successfully: {result.data}")





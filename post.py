import os

import tweepy
from openai import OpenAI


required = [
    "OPENAI_API_KEY",
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
]

missing = [name for name in required if not os.getenv(name)]
if missing:
    raise RuntimeError(f"Missing secrets: {', '.join(missing)}")


openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

prompt = """
Xに投稿する日本語の文章を1つ作ってください。

アカウントのテーマ：
・AI
・投資
・XRP
・タイ生活
・不動産
・実際に試した体験や率直な感想

条件：
・自然な個人の投稿にする
・煽りすぎない
・断定的な投資助言をしない
・220文字以内
・ハッシュタグは最大2個
・前置きや説明を付けず、投稿本文だけを出力する
"""

response = openai_client.responses.create(
    model="gpt-5-mini",
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
import tweepy

required = [
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
]

missing = [name for name in required if not os.getenv(name)]
if missing:
    raise RuntimeError(f"Missing secrets: {', '.join(missing)}")

client = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
)

text = "X自動投稿のテストです。GitHub Actionsから投稿しました。"

response = client.create_tweet(text=text)
print(f"Posted successfully: {response.data}")

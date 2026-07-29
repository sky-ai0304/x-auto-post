import os
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

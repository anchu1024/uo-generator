import os
import discord

TOKEN = os.getenv("DISCORD_TOKEN")

# Botのインテント（権限）を設定
intents = discord.Intents.default()
intents.message_content = True  # メッセージの内容を読み取るために必須

client = discord.Client(intents=intents)

# 送りたいGIFのURL（Discord上に表示したいGIFのリンク）
# ※GIPHYやTenorのリンク、またはDiscordにアップロードした画像のURLなど
GIF_URL = "ここに送りたいGIFのURLを貼り付ける"

@client.event
async def on_ready():
    print(f"ログインしました: {client.user}")

@client.event
async def on_message(message):
    # Bot自身のメッセージには反応しないようにする（無限ループ防止）
    if message.author == client.user:
        return

    # メッセージのテキストに「うお」が含まれているか判定
    if "うお" in message.content:
        # 即刻GIFを送信
        await message.channel.send(GIF_URL)

# 事前準備で取得したBotのトークンを入力
client.run(TOKEN)
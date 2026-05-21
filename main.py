import os
import discord
from flask import Flask, request, abort
from threading import Thread

# ==========================================
# 1. 叩き起こされるためのWebサーバー設定 (Flask)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    secret_token = os.getenv("WEB_SECRET_TOKEN")
    user_token = request.args.get('token')
    if not secret_token or user_token != secret_token:
        abort(403)  # 不正アクセスとして弾く！
    # 叩き起こしサービスがアクセスしてきたら「生きてるよ」と返す
    return "Botは正常に稼働しています！"

def run_flask():
    # Renderはデフォルトでポート10000番を使用するため指定
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    # Discord Botとは別のスレッド（裏側）でWebサーバーを起動する
    t = Thread(target=run_flask)
    t.start()

# ここで先にWebサーバーを裏側で起動してしまう！
keep_alive()


# ==========================================
# 2. Discord Botの設定
# ==========================================
# Botのインテント（権限）を設定
intents = discord.Intents.default()
intents.message_content = True  # メッセージの内容を読み取るために必須

client = discord.Client(intents=intents)

# 送りたいGIFのURL
GIF_URL = {"uo": "https://raw.githubusercontent.com/anchu1024/uo-generator/7661fcbb07bcdb51abafc5d4fb751c18dd38447b/uo.gif", "kamen": "https://raw.githubusercontent.com/anchu1024/uo-generator/d0943f11d73ac6d91b2eb2a99beea8aa08250ebd/kamen.gif"}

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
        await message.channel.send(GIF_URL["uo"])
    if "仮面" in message.content or "平均値" in message.content:
        await message.channel.send(GIF_URL["kamen"])

# ==========================================
# 3. 最後にDiscord Botを起動
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
client.run(TOKEN)
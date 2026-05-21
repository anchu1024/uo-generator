import os
import asyncio
import requests
import json
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
intents.members = True

client = discord.Client(intents=intents)

# 送りたいGIFのURL
GIF_URL = {"uo": "https://raw.githubusercontent.com/anchu1024/uo-generator/7661fcbb07bcdb51abafc5d4fb751c18dd38447b/uo.gif", "kamen": "https://raw.githubusercontent.com/anchu1024/uo-generator/d0943f11d73ac6d91b2eb2a99beea8aa08250ebd/kamen.gif"}

PAT = os.getenv("GITHUB_PAT")
GIST_ID = os.getenv("GIST_ID")
DATA_FILE = "targets.json"

def save_json(data):
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {"Authorization": f"token {PAT}"}

    # JSON保存用に、サーバーID（キー）を文字列に、ユーザーID（値）をリストに変換
    payload_data = {str(gid): list(uids) for gid, uids in data.items()}

    payload = {
        "files": {
            DATA_FILE: {
                "content": json.dumps(payload_data, ensure_ascii=False, indent=2)
            }
        }
    }

    res = requests.patch(url, headers=headers, json=payload)
    return res.json()

def load_json():
    url = f"https://api.github.com/gists/{GIST_ID}"
    try:
        res = requests.get(url)
        res_json = res.json()
        
        # Gistの中に指定したファイルが存在するかチェック
        if "files" in res_json and DATA_FILE in res_json["files"]:
            raw = res_json["files"][DATA_FILE]["content"]
            if raw.strip(): # 空っぽでなければパース
                loaded_data = json.loads(raw)
                # 💡【重要】JSONの文字列キーを、Pythonで扱いやすい「数値(int)のキー」に変換
                # 重複を自動で弾くために、ユーザーIDリストも set に変換します
                return {int(gid): set(uids) for gid, uids in loaded_data.items()}
    except Exception as e:
        print(f"【警告】Gistの読み込みに失敗しました。新規データとして開始します。エラー: {e}")
    return {}

# --- 非同期にラップした関数 ---
async def async_save_json(data):
    # loop.run_in_executor を使って裏のスレッドプールで実行
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, save_json, data)

async def async_load_json():
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, load_json)

GUILD_TARGETS = {}

@client.event
async def on_ready():
    global GUILD_TARGETS
    print(f"ログインしました: {client.user}")
    GUILD_TARGETS = await async_load_json()

@client.event
async def on_message(message):
    # Bot自身のメッセージには反応しないようにする（無限ループ防止）
    if message.guild is None or message.author == client.user:
        return
    
    guild_id = message.guild.id  # 現在のサーバーIDを取得
    if message.content.startswith("::set "):
        # コマンドを打った本人（メッセージの送信者）のIDを取得
        author_id = message.author.id

        target_name = message.content[6:].strip()
        if not target_name:
            await message.reply("ユーザー名を入力してください。")
            return
        
        target_member = None
        try:
            found_members = await message.guild.query_members(query=target_name, limit=1)
            if found_members:
                target_member = found_members[0]
        except Exception:
            # 念のため従来のキャッシュ検索もフォールバックとして残す
            target_member = discord.utils.get(message.guild.members, name=target_name)

        if target_member:
            if target_member.id == author_id:
                await message.reply("自分で自分に関する操作はできないよ...")
                return
            # このサーバーのリストがまだ辞書になければ初期化
            if guild_id not in GUILD_TARGETS:
                GUILD_TARGETS[guild_id] = set()
            
            if target_member.id in GUILD_TARGETS[guild_id]:
                await message.reply(f"「{target_member.display_name}」はすでに登録されています。")
                return
            GUILD_TARGETS[guild_id].add(target_member.id)
            await async_save_json(GUILD_TARGETS)  # データを保存
            await message.reply(f"このサーバーの対象として {target_member.display_name} を登録しました！")
        else:
            await message.reply(f"「{target_name}」が見つかりませんでした。")
        return
    
    if message.content.startswith("::unset "):
        author_id = message.author.id
        target_name = message.content[8:].strip()
        
        # 💡 解除時も同様に検索を確実に
        target_member = None
        try:
            found_members = await message.guild.query_members(query=target_name, limit=1)
            if found_members:
                target_member = found_members[0]
        except Exception:
            target_member = discord.utils.get(message.guild.members, name=target_name)

        if target_member:
            if target_member.id == author_id:
                await message.reply("自分で自分に関する操作はできないよ...")
                return
            if guild_id in GUILD_TARGETS and target_member.id in GUILD_TARGETS[guild_id]:
                GUILD_TARGETS[guild_id].remove(target_member.id)
                await async_save_json(GUILD_TARGETS)  # データを保存
                await message.reply(f"{target_member.display_name} をこのサーバーのリストから解除しました。")
            else:
                await message.reply(f"「{target_name}」は登録されていません。")
            return
    
    # ------------------------------------------
    # 🐟 通常のメッセージ判定
    # ------------------------------------------
    # このサーバー用のターゲットリストが存在し、かつ発言者がその中にいるか判定
    if guild_id in GUILD_TARGETS and message.author.id in GUILD_TARGETS[guild_id]:
        await message.reply("うおww")
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
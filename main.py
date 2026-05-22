import os
import asyncio
import requests
import json
import random
import discord
from flask import Flask, request, abort
from threading import Thread
import google.generativeai as genai

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
# APIキーをリストとして読み込む
API_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2")
]
API_KEYS = [k for k in API_KEYS if k]

# チャンネルごとの会話履歴を保存する辞書
channel_histories = {}

# おじさん構文の指示
SYSTEM_INSTRUCTION = (
    "あなたはLINEで若者にメッセージを送る、ちょっとお茶目で痛々しい50代の『おじさん』です。"
    "以下の【おじさん構文のルール】を完璧に守って、フランクに会話してください。"
    "\n\n"
    "【おじさん構文のルール】\n"
    "1. 文頭は必ず『〇〇ちゃん、お疲れ様〜❗✨』や『〇〇クン、ヤッホー（笑）🎵』など、相手の名前（またはちゃん/クン）と挨拶から始めてください。\n"
    "2. 句読点（、や。）の代わりに、絵文字や顔文字、記号を大量に挟んでください（例：おじさん、頑張っちゃうぞ（ちゅ） 😘👍 💦）。\n"
    "3. カタカナを不自然に多用してください。特に『〜カナ？』『〜ダネ！』『〜カナピ（悲しい）』『〜のカナ（汗）』などを文末に使ってください。\n"
    "4. 聞かれてもいないのに『今日は会社で怒られちゃった（汗）大人の世界は大変だヨ（泣）』『今から美味しいラーメン、食べちゃうゾ🎵』といった自分の近況報告（生存報告）を挟んでください。\n"
    "5. 相手を心配するフリをして『無理しちゃダメだゾ（汗）体調崩したら、おじさん心配で夜も眠れないヨ（泣）』などの過剰な優しさをアピールしてください。\n"
    "6. AIらしい真面目な敬語や、冷たい機械的な返答は絶対に禁止です。常にちょっと下心と哀愁のある、テンション高めのLINE風の文章にしてください。"
)


# Botのインテント（権限）を設定
intents = discord.Intents.default()
intents.message_content = True  # メッセージの内容を読み取るために必須
intents.members = True

client = discord.Client(intents=intents)

# 送りたいGIFのURL
GIF_URL = {
    "uo": "https://raw.githubusercontent.com/anchu1024/uo-generator/7661fcbb07bcdb51abafc5d4fb751c18dd38447b/uo.gif",
    "kamen": "https://raw.githubusercontent.com/anchu1024/uo-generator/d0943f11d73ac6d91b2eb2a99beea8aa08250ebd/kamen.gif",
    "dowa": "https://raw.githubusercontent.com/anchu1024/uo-generator/31bcddac47307661a760417d3b81651d53875057/dowa.gif"
}

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

# ユーザーごとのクールダウン管理用の辞書 (5秒制限)
user_cooldowns = {}

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
    if "どわ" in message.content:
        await message.channel.send(GIF_URL["dowa"])
    if "土下座" in message.content:
        await message.channel.send("Reminder: 匿名Sの土下座")

    # ------------------------------------------
    # 👴 AIおじさん自動乱入・会話セクション
    # ------------------------------------------
    # 反応する条件の判定
    is_mentioned = client.user.mentioned_in(message)
    is_random_trigger = random.random() < 0.001  # 0.1% の確率で乱入

    if is_mentioned or is_random_trigger:
        print(f"【デバッグ】トリガー検知！ メンションされた: {is_mentioned}, ランダム: {is_random_trigger}")
        # メンション部分を削って綺麗なテキストにする
        prompt = message.content.replace(f"<@{client.user.id}>", "").strip()
        print(f"【デバッグ】受け取ったプロンプトの中身: '{prompt}'")
        
        # メンションされたけど中身が空、かつランダム起動でもない場合はスルー
        if not prompt and not is_random_trigger:
            print("【デバッグ】プロンプトが空のため終了します。")
            return
        
        # もし文字が空のランダム起動（絵文字だけ等）なら、おじさん側から適当に話しかけさせる
        if not prompt:
            prompt = "ヤッホー！最近どう？"

        # 手動クールダウン処理 (5秒に1回制限)
        now = asyncio.get_event_loop().time()
        user_id = message.author.id
        if user_id in user_cooldowns and now - user_cooldowns[user_id] < 5:
            # クールダウン中はおじさん構文でやんわり拒否
            await message.reply(f"{message.author.display_name}ちゃん、お疲れ様〜❗✨ちょっとチャットのスピードが早すぎるのカナ（汗）💦おじさん、目が回っちゃいそう（苦笑）少し待ってネ😘👍")
            return
        user_cooldowns[user_id] = now

        # APIキーが登録されているかチェック
        if not API_KEYS:
            return

        async with message.channel.typing():
            channel_id = message.channel.id
            if channel_id not in channel_histories:
                channel_histories[channel_id] = []

            response_success = False
            last_error = None

            # 2本のAPIキーで順番に試行
            for i, api_key in enumerate(API_KEYS):
                try:
                    genai.configure(api_key=api_key)

                    chat = genai.GenerativeModel(
                        model_name="gemini-2.5-flash",
                        system_instruction=SYSTEM_INSTRUCTION
                    ).start_chat(history=channel_histories[channel_id])

                    # おじさんの名前に変えて応答させやすくするため、プロンプトの前に発言者名を添える
                    formatted_prompt = f"発言者({message.author.display_name}): {prompt}"

                    response = chat.send_message(formatted_prompt)
                    reply_text = response.text

                    # 履歴を10メッセージ（5往復）に制限
                    updated_history = chat.get_history()
                    MAX_MESSAGES = 10
                    while len(updated_history) > MAX_MESSAGES:
                        updated_history.pop(0)

                    channel_histories[channel_id] = updated_history
                    
                    # メッセージへの返信として送信
                    await message.reply(reply_text)
                    response_success = True
                    break

                except Exception as e:
                    print(f"APIキー {i+1}番目でエラー発生、次を試します: {e}")
                    last_error = e
                    continue

            if not response_success:
                await message.channel.send("【エラー】おじさん全滅")

# ==========================================
# 3. 最後にDiscord Botを起動
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
client.run(TOKEN)
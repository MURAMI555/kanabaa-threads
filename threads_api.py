"""Threads API（叶ばぁ＋キャラ4本用）。Meta開発者アプリで取った長期トークンで投稿する。
投稿は2段階：コンテナ作成 → 公開。画像は公開URL（GitHubのraw）を渡す。返信は reply_to_id。
トークンは60日で切れる。週1で更新し、RENDER_API_KEY があれば Render の環境変数も書き換える。

2026/10/22 複数アカウント対応：account は "kanabaa"（既定・叶ばぁ）か、"mio"（澪）"tsumugi"（紬）"rin"（鈴）"ritsu"（律）。
  既定の環境変数   THREADS_ACCESS_TOKEN / THREADS_USER_ID
  ほかのアカウント THREADS_ACCESS_TOKEN_MIO / THREADS_USER_ID_MIO のように、キーを大文字にして後ろに付ける"""
import os
import time

import requests

BASE = "https://graph.threads.net/v1.0"
DEFAULT = "kanabaa"
ACCOUNTS = ["kanabaa", "mio", "tsumugi", "rin", "ritsu"]
_mem_token: dict = {}  # account -> 更新後のトークン（プロセスが生きている間だけ）


def env_name(base: str, account: str = DEFAULT) -> str:
    """環境変数の名前。既定アカウントは接尾辞なし"""
    return base if account == DEFAULT else f"{base}_{account.upper()}"


def token(account: str = DEFAULT) -> str:
    return (_mem_token.get(account) or os.environ.get(env_name("THREADS_ACCESS_TOKEN", account), "")).strip()


def set_token(t: str, account: str = DEFAULT):
    _mem_token[account] = t.strip()


def user_id(account: str = DEFAULT) -> str:
    return os.environ.get(env_name("THREADS_USER_ID", account), "").strip() or "me"


def configured(account: str = DEFAULT) -> bool:
    return bool(token(account))


def configured_accounts() -> list:
    return [a for a in ACCOUNTS if configured(a)]


def me(account: str = DEFAULT) -> dict:
    r = requests.get(f"{BASE}/me", params={"fields": "id,username", "access_token": token(account)}, timeout=30)
    r.raise_for_status()
    return r.json()


def _wait_ready(creation_id: str, account: str = DEFAULT, tries: int = 12):
    """画像つきコンテナは処理待ちがあるので、公開できる状態になるまで待つ（最長およそ1分）"""
    for _ in range(tries):
        r = requests.get(f"{BASE}/{creation_id}", params={"fields": "status,error_message", "access_token": token(account)}, timeout=30)
        if r.ok:
            st = r.json().get("status")
            if st == "FINISHED":
                return
            if st == "ERROR":
                raise RuntimeError("コンテナ作成に失敗: " + str(r.json().get("error_message")))
        time.sleep(5)


def post(text: str, image_url: str | None = None, reply_to_id: str | None = None, account: str = DEFAULT) -> str:
    """投稿して、公開後のIDを返す"""
    if not configured(account):
        raise RuntimeError(env_name("THREADS_ACCESS_TOKEN", account) + " が未設定")
    data = {"text": text, "access_token": token(account)}
    if image_url:
        data["media_type"] = "IMAGE"
        data["image_url"] = image_url
    else:
        data["media_type"] = "TEXT"
    if reply_to_id:
        data["reply_to_id"] = reply_to_id
    r = requests.post(f"{BASE}/{user_id(account)}/threads", data=data, timeout=60)
    r.raise_for_status()
    creation_id = r.json()["id"]
    if image_url:
        _wait_ready(creation_id, account)
    r2 = requests.post(f"{BASE}/{user_id(account)}/threads_publish",
                       data={"creation_id": creation_id, "access_token": token(account)}, timeout=60)
    r2.raise_for_status()
    return r2.json()["id"]


def my_posts(limit: int = 25, account: str = DEFAULT) -> list:
    """自分の最近の投稿（新しい順）。二重投稿の確認に使う"""
    r = requests.get(f"{BASE}/{user_id(account)}/threads",
                     params={"fields": "id,text,timestamp", "limit": limit, "access_token": token(account)}, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def conversation(media_id: str, account: str = DEFAULT) -> list:
    """投稿についた返信ぜんぶ（ツリーの下まで）。受付箱が生年月日コメントを拾うのに使う。読むだけ"""
    r = requests.get(f"{BASE}/{media_id}/conversation", params={
        "fields": "id,text,username,timestamp,permalink,replied_to,is_reply_owned_by_me,hide_status",
        "reverse": "false", "limit": 100, "access_token": token(account)}, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def publishing_limit(account: str = DEFAULT) -> dict:
    r = requests.get(f"{BASE}/{user_id(account)}/threads_publishing_limit",
                     params={"fields": "quota_usage,config", "access_token": token(account)}, timeout=30)
    r.raise_for_status()
    data = r.json().get("data") or [{}]
    return data[0]


def refresh_token(account: str = DEFAULT) -> str:
    """長期トークンを新しくする（また60日使える）。発行から24時間たってから使える"""
    r = requests.get("https://graph.threads.net/refresh_access_token",
                     params={"grant_type": "th_refresh_token", "access_token": token(account)}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def exchange_code(app_id: str, app_secret: str, redirect_uri: str, code: str) -> str:
    """OAuthのcode → 短期トークン → 長期トークン（60日）"""
    r = requests.post("https://graph.threads.net/oauth/access_token", data={
        "client_id": app_id, "client_secret": app_secret, "grant_type": "authorization_code",
        "redirect_uri": redirect_uri, "code": code}, timeout=30)
    r.raise_for_status()
    short = r.json()["access_token"]
    r2 = requests.get("https://graph.threads.net/access_token", params={
        "grant_type": "th_exchange_token", "client_secret": app_secret, "access_token": short}, timeout=30)
    r2.raise_for_status()
    return r2.json()["access_token"]


def save_token_to_render(new_token: str, account: str = DEFAULT) -> bool:
    """Render の環境変数 THREADS_ACCESS_TOKEN（アカウント別の名前）を書き換える（RENDER_API_KEY と RENDER_SERVICE_ID がある時だけ）。再デプロイが走る"""
    key = os.environ.get("RENDER_API_KEY", "").strip()
    sid = os.environ.get("RENDER_SERVICE_ID", "").strip()
    if not key or not sid:
        return False
    r = requests.put(f"https://api.render.com/v1/services/{sid}/env-vars/{env_name('THREADS_ACCESS_TOKEN', account)}",
                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                     json={"value": new_token}, timeout=30)
    r.raise_for_status()
    return True

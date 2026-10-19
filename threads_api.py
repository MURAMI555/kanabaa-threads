"""Threads API（叶ばぁ用）。Meta開発者アプリで取った長期トークンで投稿する。
投稿は2段階：コンテナ作成 → 公開。画像は公開URL（GitHubのraw）を渡す。返信は reply_to_id。
トークンは60日で切れる。週1で更新し、RENDER_API_KEY があれば Render の環境変数も書き換える。"""
import os
import time

import requests

BASE = "https://graph.threads.net/v1.0"
_mem_token = None  # 更新後のトークン（プロセスが生きている間だけ）


def token() -> str:
    return (_mem_token or os.environ.get("THREADS_ACCESS_TOKEN", "")).strip()


def set_token(t: str):
    global _mem_token
    _mem_token = t.strip()


def user_id() -> str:
    return os.environ.get("THREADS_USER_ID", "").strip() or "me"


def configured() -> bool:
    return bool(token())


def me() -> dict:
    r = requests.get(f"{BASE}/me", params={"fields": "id,username", "access_token": token()}, timeout=30)
    r.raise_for_status()
    return r.json()


def _wait_ready(creation_id: str, tries: int = 12):
    """画像つきコンテナは処理待ちがあるので、公開できる状態になるまで待つ（最長およそ1分）"""
    for _ in range(tries):
        r = requests.get(f"{BASE}/{creation_id}", params={"fields": "status,error_message", "access_token": token()}, timeout=30)
        if r.ok:
            st = r.json().get("status")
            if st == "FINISHED":
                return
            if st == "ERROR":
                raise RuntimeError("コンテナ作成に失敗: " + str(r.json().get("error_message")))
        time.sleep(5)


def post(text: str, image_url: str | None = None, reply_to_id: str | None = None) -> str:
    """投稿して、公開後のIDを返す"""
    if not configured():
        raise RuntimeError("THREADS_ACCESS_TOKEN が未設定")
    data = {"text": text, "access_token": token()}
    if image_url:
        data["media_type"] = "IMAGE"
        data["image_url"] = image_url
    else:
        data["media_type"] = "TEXT"
    if reply_to_id:
        data["reply_to_id"] = reply_to_id
    r = requests.post(f"{BASE}/{user_id()}/threads", data=data, timeout=60)
    r.raise_for_status()
    creation_id = r.json()["id"]
    if image_url:
        _wait_ready(creation_id)
    r2 = requests.post(f"{BASE}/{user_id()}/threads_publish",
                       data={"creation_id": creation_id, "access_token": token()}, timeout=60)
    r2.raise_for_status()
    return r2.json()["id"]


def my_posts(limit: int = 25) -> list:
    """自分の最近の投稿（新しい順）。二重投稿の確認に使う"""
    r = requests.get(f"{BASE}/{user_id()}/threads",
                     params={"fields": "id,text,timestamp", "limit": limit, "access_token": token()}, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def publishing_limit() -> dict:
    r = requests.get(f"{BASE}/{user_id()}/threads_publishing_limit",
                     params={"fields": "quota_usage,config", "access_token": token()}, timeout=30)
    r.raise_for_status()
    data = r.json().get("data") or [{}]
    return data[0]


def refresh_token() -> str:
    """長期トークンを新しくする（また60日使える）。発行から24時間たってから使える"""
    r = requests.get("https://graph.threads.net/refresh_access_token",
                     params={"grant_type": "th_refresh_token", "access_token": token()}, timeout=30)
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


def save_token_to_render(new_token: str) -> bool:
    """Render の環境変数 THREADS_ACCESS_TOKEN を書き換える（RENDER_API_KEY と RENDER_SERVICE_ID がある時だけ）。再デプロイが走る"""
    key = os.environ.get("RENDER_API_KEY", "").strip()
    sid = os.environ.get("RENDER_SERVICE_ID", "").strip()
    if not key or not sid:
        return False
    r = requests.put(f"https://api.render.com/v1/services/{sid}/env-vars/THREADS_ACCESS_TOKEN",
                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                     json={"value": new_token}, timeout=30)
    r.raise_for_status()
    return True

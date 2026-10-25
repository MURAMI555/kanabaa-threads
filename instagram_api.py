"""Instagram API（Instagramログイン版・Facebookページ不要）。2026/10/25 鈴（rin）から。
プロアカウント（クリエイター/ビジネス）の長期トークンで、フィードに画像1枚かカルーセル（2〜10枚）を投稿する。
投稿は2段階：コンテナ作成 → 公開。画像は公開URL（GitHubのraw・JPEG）を渡す。
トークンは60日で切れる。週1で更新し、RENDER_API_KEY があれば Render の環境変数も書き換える。

環境変数は IG_ACCESS_TOKEN_RIN のように、アカウント名を大文字にして後ろに付ける（Threads と違い既定アカウントは無い）。"""
import os
import time

import requests

BASE = "https://graph.instagram.com/v21.0"
ACCOUNTS = ["rin"]
_mem_token: dict = {}  # account -> 更新後のトークン（プロセスが生きている間だけ）


def env_name(account: str) -> str:
    return f"IG_ACCESS_TOKEN_{account.upper()}"


def token(account: str) -> str:
    return (_mem_token.get(account) or os.environ.get(env_name(account), "")).strip()


def set_token(t: str, account: str):
    _mem_token[account] = t.strip()


def configured(account: str) -> bool:
    return bool(token(account))


def configured_accounts() -> list:
    return [a for a in ACCOUNTS if configured(a)]


def me(account: str) -> dict:
    r = requests.get(f"{BASE}/me", params={"fields": "user_id,username,account_type", "access_token": token(account)}, timeout=30)
    r.raise_for_status()
    return r.json()


def _wait_ready(container_id: str, account: str, tries: int = 24):
    """コンテナの処理待ち（最長およそ2分）"""
    for _ in range(tries):
        r = requests.get(f"{BASE}/{container_id}", params={"fields": "status_code,status", "access_token": token(account)}, timeout=30)
        if r.ok:
            st = r.json().get("status_code")
            if st == "FINISHED":
                return
            if st in ("ERROR", "EXPIRED"):
                raise RuntimeError("コンテナ作成に失敗: " + str(r.json().get("status")))
        time.sleep(5)
    raise RuntimeError("コンテナの処理が終わらない: " + container_id)


def _container(account: str, **data) -> str:
    data["access_token"] = token(account)
    r = requests.post(f"{BASE}/me/media", data=data, timeout=60)
    if not r.ok:
        raise RuntimeError(f"コンテナ作成エラー {r.status_code}: {r.text[:300]}")
    return r.json()["id"]


def post(caption: str, image_urls: list, account: str) -> str:
    """画像1枚なら単体、2枚以上ならカルーセルで投稿して、公開後のIDを返す"""
    if not configured(account):
        raise RuntimeError(env_name(account) + " が未設定")
    if not image_urls:
        raise RuntimeError("画像がない（インスタは画像が要る）")
    if len(image_urls) == 1:
        cid = _container(account, image_url=image_urls[0], caption=caption)
    else:
        children = []
        for u in image_urls[:10]:
            c = _container(account, image_url=u, is_carousel_item="true")
            _wait_ready(c, account)
            children.append(c)
        cid = _container(account, media_type="CAROUSEL", children=",".join(children), caption=caption)
    _wait_ready(cid, account)
    r = requests.post(f"{BASE}/me/media_publish", data={"creation_id": cid, "access_token": token(account)}, timeout=60)
    if not r.ok:
        raise RuntimeError(f"公開エラー {r.status_code}: {r.text[:300]}")
    return r.json()["id"]


def my_posts(account: str, limit: int = 10) -> list:
    """自分の最近の投稿（新しい順）。二重投稿の確認に使う"""
    r = requests.get(f"{BASE}/me/media", params={"fields": "id,caption,timestamp,permalink", "limit": limit,
                                                 "access_token": token(account)}, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


STAT_METRICS = ["views", "reach", "likes", "comments", "saved", "shares"]


def profile(account: str) -> dict:
    r = requests.get(f"{BASE}/me", params={"fields": "username,followers_count,media_count",
                                           "access_token": token(account)}, timeout=30)
    r.raise_for_status()
    return r.json()


def media_stats(account: str, limit: int = 20) -> list:
    """最近の投稿ごとの閲覧数など（新しい順）。2026/10/25 追加。
    instagram_business_manage_insights の権限が要る。取れない投稿は "error" に理由を入れる"""
    r = requests.get(f"{BASE}/me/media", params={"fields": "id,caption,timestamp,permalink,media_type,like_count,comments_count",
                                                 "limit": limit, "access_token": token(account)}, timeout=30)
    r.raise_for_status()
    out = []
    for p in r.json().get("data", []):
        row = {"id": p["id"], "timestamp": p.get("timestamp"), "permalink": p.get("permalink"),
               "media_type": p.get("media_type"), "caption": (p.get("caption") or "").strip().splitlines()[0][:40] if p.get("caption") else "",
               "likes": p.get("like_count"), "comments": p.get("comments_count")}
        ir = requests.get(f"{BASE}/{p['id']}/insights", params={"metric": ",".join(STAT_METRICS),
                                                               "access_token": token(account)}, timeout=30)
        if ir.ok:
            for m in ir.json().get("data", []):
                vals = m.get("values") or [{}]
                row[m["name"]] = m.get("total_value", {}).get("value", vals[0].get("value"))
        else:
            row["error"] = ir.text[:200]
        out.append(row)
    return out


def publishing_limit(account: str) -> dict:
    r = requests.get(f"{BASE}/me/content_publishing_limit", params={"fields": "quota_usage,config",
                                                                     "access_token": token(account)}, timeout=30)
    r.raise_for_status()
    data = r.json().get("data") or [{}]
    return data[0]


def refresh_token(account: str) -> str:
    """長期トークンを新しくする（また60日使える）。発行から24時間たってから使える"""
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": token(account)}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def save_token_to_render(new_token: str, account: str) -> bool:
    """Render の環境変数 IG_ACCESS_TOKEN_<名前> を書き換える（RENDER_API_KEY と RENDER_SERVICE_ID がある時だけ）"""
    key = os.environ.get("RENDER_API_KEY", "").strip()
    sid = os.environ.get("RENDER_SERVICE_ID", "").strip()
    if not key or not sid:
        return False
    r = requests.put(f"https://api.render.com/v1/services/{sid}/env-vars/{env_name(account)}",
                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                     json={"value": new_token}, timeout=30)
    r.raise_for_status()
    return True

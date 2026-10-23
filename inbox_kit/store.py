"""受付箱の置き場（Googleスプレッドシート＋Apps Script の Web アプリ。gas/kanabaa_inbox.gs）。
Render の無料サーバーは再起動で中身が消えるので、お客様のメッセージと下書きはシートに置く。
環境変数 INBOX_STORE_URL（Web アプリの /exec URL）と INBOX_STORE_KEY（gs と同じ合言葉）。
1件＝1行。id（th:コメントID / line:ユーザーID）・kind・status・updated・data(JSON)。"""
import json
import os
import threading
import time

import requests

_lock = threading.Lock()
_cache = {"at": 0.0, "items": {}}


def configured() -> bool:
    return bool(os.environ.get("INBOX_STORE_URL") and os.environ.get("INBOX_STORE_KEY"))


def _call(payload: dict) -> dict:
    payload = dict(payload, key=os.environ.get("INBOX_STORE_KEY", ""))
    r = requests.post(os.environ["INBOX_STORE_URL"], data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, timeout=60)
    r.raise_for_status()
    res = r.json()
    if res.get("error"):
        raise RuntimeError("受付箱シート: " + str(res["error"]))
    return res


def all_items(max_age: int = 60) -> dict:
    """id → item（{id, kind, status, updated, ...data}）。60秒はメモリの写しを使う"""
    with _lock:
        if time.time() - _cache["at"] < max_age and _cache["items"]:
            return dict(_cache["items"])
        rows = _call({"op": "list"}).get("rows", [])
        items = {}
        for row in rows:
            try:
                data = json.loads(row.get("data") or "{}")
            except ValueError:
                data = {}
            data.update({"id": row["id"], "kind": row["kind"], "status": row["status"], "updated": row["updated"]})
            items[row["id"]] = data
        _cache.update(at=time.time(), items=items)
        return dict(items)


def get(item_id: str):
    return all_items().get(item_id)


def put(item: dict):
    """1件を書く（あれば上書き）。updated はここで入れる"""
    item = dict(item)
    item["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data = {k: v for k, v in item.items() if k not in ("id", "kind", "status", "updated")}
    _call({"op": "upsert", "id": item["id"], "kind": item["kind"], "status": item.get("status", "new"),
           "updated": item["updated"], "data": json.dumps(data, ensure_ascii=False)})
    with _lock:
        _cache["items"][item["id"]] = item
    return item

// 叶ばぁ 受付箱の置き場（Googleスプレッドシートにつける Apps Script）。
// 使い方：新しいスプレッドシート →「拡張機能」→「Apps Script」→ これを全部貼る
// → 下の KEY を Render の INBOX_STORE_KEY と同じ文字にする（このファイルは公開リポなので、ここには本物を書かない）
// →「デプロイ」→「新しいデプロイ」→ 種類「ウェブアプリ」・実行ユーザー「自分」・アクセス「全員」→ 出た /exec の URL を Render の INBOX_STORE_URL へ。
const KEY = 'ここに合言葉';
const SHEET = '受付箱';
const HEAD = ['id', 'kind', 'status', 'updated', 'data'];

function sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(SHEET);
  if (!sh) {
    sh = ss.insertSheet(SHEET);
    sh.getRange(1, 1, 1, HEAD.length).setValues([HEAD]);
    sh.setFrozenRows(1);
  }
  return sh;
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  let req;
  try { req = JSON.parse(e.postData.contents); } catch (err) { return out_({ error: 'bad json' }); }
  if (req.key !== KEY) return out_({ error: 'key' });
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const sh = sheet_();
    const last = sh.getLastRow();
    if (req.op === 'list') {
      const vals = last > 1 ? sh.getRange(2, 1, last - 1, HEAD.length).getValues() : [];
      return out_({ rows: vals.map(v => ({ id: String(v[0]), kind: v[1], status: v[2], updated: String(v[3]), data: v[4] })) });
    }
    if (req.op === 'upsert') {
      const row = [req.id, req.kind, req.status, req.updated, req.data];
      const hit = last > 1 ? sh.getRange(2, 1, last - 1, 1).createTextFinder(req.id).matchEntireCell(true).findNext() : null;
      if (hit) sh.getRange(hit.getRow(), 1, 1, HEAD.length).setValues([row]);
      else sh.appendRow(row);
      return out_({ ok: true });
    }
    return out_({ error: 'op' });
  } finally {
    lock.releaseLock();
  }
}

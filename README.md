# 叶ばぁ Threads 自動投稿（kanabaa-threads）

叶ばぁ（Threads @kanabaa.yoru）の投稿を、Render 上の小さなアプリから Threads 公式API で予定どおり自動で出す。
予定表は `schedule.py`（日本時間・1枠＝本体＋返信でつなぐ 1/3・2/3・3/3）。線画は `img/`（GitHub の raw URL で Threads に渡す）。
返信・DM は本部ルールどおり自動で送らない（人が返す）。2026/10/23 から**下書きだけ**自動で作る受付箱あり（下の「受付箱」）。

- 5分おきに予定表を見て、時間が来た枠を投稿（30分以内の遅れなら出す）
- 二重投稿防止：投稿済みの記憶 ＋ Threads 上の直近投稿と本文の先頭を照合
- 長期トークン（60日）は毎週月曜に自動更新。`RENDER_API_KEY` と `RENDER_SERVICE_ID` があれば Render の環境変数も書き換える
- `/health` 生存確認（UptimeRobot 用）／`/status` 予定と結果／`/check` 接続確認（投稿しない）／`/oauth/start` トークン取得

## 受付箱（2026/10/23・下書きだけ自動。送るのはみかちゃん）

コードは `inbox_kit/`。このアプリからは Threads にも LINE にも**何も送らない**（本部⑥「自動返信ツールは使わない」。1タップ送信は本部の答えが来てから）。

- **Threads**：15分おきに、直近10日の叶ばぁの投稿についたコメントを読む。生年月日があれば Claude（claude-opus-5-5）が返信の下書きを作る。叶ばぁが返信したコメントは自動で「送った」。「死にたい」などは占わず窓口の文
- **LINE（@492vxwcy）**：Messaging API の Webhook `/line/webhook` で届いたメッセージを貯め、最後のメッセージから10分たったら初視（無料鑑定）の下書き。霊視メモを書いて「作り直す」と、メモを芯に書き直す。初視を「送った」あとに「本鑑定」と来たら、本鑑定の案内文（`SQUARE_URL`）
- **画面**：`https://kanabaa-threads.onrender.com/inbox?pin=合言葉`（1回開けば180日そのスマホで入れる）。コピー → Threads／LINEのアプリで貼って送る →「送った」
- お客様のメッセージと下書きはスプレッドシート（`gas/kanabaa_inbox.gs`）に置く。Render は再起動で中身が消えるため
- 下書きは叶ばぁの禁止語チェック（`inbox_kit/kinshi.py`）を通し、引っかかったら1回直させる。残ったら画面に赤字
- Threads の返信の最後の1行は、2026/10/25 から「プロフィールのリンクから婆さんのLINEへ」（それまでは「インスタのDMへ」）

### 受付箱の設定（みかちゃんの手）

合言葉2つ（`INBOX_PIN`・`INBOX_STORE_KEY`）は PC の `~/.claude/secrets/kanabaa-inbox.env` にある（公開リポには書かない）。

1. **置き場のシート**：新しいスプレッドシート「叶ばぁ_受付箱」→ 拡張機能 → Apps Script → `gas/kanabaa_inbox.gs` を貼り、`KEY` を `INBOX_STORE_KEY` の値に → デプロイ → 新しいデプロイ → ウェブアプリ・実行ユーザー「自分」・アクセス「全員」→ 許可 → 出た `/exec` のURLを控える
2. **LINE の Messaging API**：LINE公式アカウントの管理画面（叶ばぁ）→ 設定 → Messaging API →「Messaging APIを利用する」→ プロバイダー「叶ばぁ」→ チャネルシークレットを控える。LINE Developers のそのチャネル → Messaging API設定 → チャネルアクセストークン（長期）を発行 → Webhook URL に `https://kanabaa-threads.onrender.com/line/webhook` →「Webhookの利用」オン。応答設定は**チャットはオンのまま**（手で返すため）・応答メッセージはオフのまま。※Messaging API は一度オンにすると戻せない
3. **Render の環境変数**（kanabaa-threads）に入れる：`INBOX_PIN`・`INBOX_STORE_KEY`・`INBOX_STORE_URL`（1のURL）・`LINE_CHANNEL_SECRET`・`LINE_CHANNEL_ACCESS_TOKEN`・`ANTHROPIC_API_KEY`（nurikae-linebot に入っているものと同じでよい）・（あれば）`SQUARE_URL`
4. `/inbox?pin=…` を開く →「今すぐ読み込む」。`/inbox/log` で設定の有無が見える

## キャラを増やすとき（2026/10/22・澪 mio／紬 tsumugi／鈴 rin／律 ritsu）

同じ Meta アプリ・同じ Render で、アカウントごとにトークンを分けて投稿する。予定表のキーは `mio@2026-10-27 08:00` のように「キャラ名@日時」（叶ばぁは今までどおり日時だけ）。トークンが入っていないキャラの枠は飛ばすので、先に予定表を入れておいても害はない。

1. そのキャラの Threads アカウントを作って、PC の Chrome でそのアカウントにログインしておく
2. Meta の開発者アプリ `kanabaa threads` →「アプリの役割」→「人を追加」→ **Threads テスター**にそのアカウント（例 mio_suuhi）を追加 → スマホの Threads アプリ（そのアカウント）→ 設定 → アカウント → ウェブサイトのアクセス許可 → 承認
3. トークンを取る（どちらか）
   - A：Meta の「ユーザートークン生成ツール」（叶ばぁのときと同じ）でそのアカウントのトークンを作る
   - B：`https://kanabaa-threads.onrender.com/oauth/start?account=mio` を開いて「許可」（App Secret が Render に入っているとき）
4. Render の環境変数に貼る：**`THREADS_ACCESS_TOKEN_MIO`**（紬は `_TSUMUGI`、鈴は `_RIN`、律は `_RITSU`）。保存すると再デプロイ
5. `https://kanabaa-threads.onrender.com/check?account=mio` で `username` がそのアカウントなら接続OK。`/status` の `accounts` で全部の状態が見える
6. 週1の自動更新は全アカウント分まわる（`RENDER_API_KEY` があれば `THREADS_ACCESS_TOKEN_MIO` も書き換える）

専用ページは `docs/<キャラ名>/index.html`（`https://murami555.github.io/kanabaa-threads/mio/` など）。LINE の友だち追加URLが決まったら各ページの `LINE_URL` に入れて push。

## 最初の設定（みかちゃんの手でやる。順番どおり）

### 1. GitHub にリポジトリを作る（公開）

1. https://github.com/new を開く（MURAMI555 でログイン）
2. Repository name：`kanabaa-threads`、**Public**、READMEなどは追加しない → Create repository
3. Claude に「作った」と言う → この PC から push する（`git push -u origin main`）
   線画の URL が `https://raw.githubusercontent.com/MURAMI555/kanabaa-threads/main/img/…` になる

### 2. Meta の開発者アプリを作る（Threads API）

1. https://developers.facebook.com/ に、みかちゃんの Facebook（Meta）アカウントでログイン。初めてなら開発者登録（電話かメールの確認あり）
2. 「マイアプリ」→「アプリを作成」→ ユースケースで **「Threads API にアクセス」** を選ぶ → アプリ名は `kanabaa threads`（何でもよい）→ 作成
3. 左メニュー「ユースケース」→ Threads API →「設定」→ 権限で `threads_basic`・`threads_content_publish`・`threads_manage_replies`・`threads_read_replies` を追加
4. 「アプリ設定」→「ベーシック」で **アプリID** と **app secret**（表示を押す）を控える（Claude には送らない。Render に直接入れる）
5. Threads API の設定画面の「リダイレクトコールバックURL」に `https://kanabaa-threads.onrender.com/oauth/callback` を入れる（Render のURLが違う名前になったら、そのURLに合わせる）。「アプリの登録解除コールバック」「データ削除のコールバック」も同じURLでよい
6. 「アプリの役割」→「役割」→「人を追加」→ **Threads テスター** として `kanabaa.yoru` を追加
7. スマホの Threads アプリ（kanabaa.yoru）→ 設定 → アカウント → **ウェブサイトのアクセス許可** → 招待を承認

### 3. Render にサービスを作る

1. https://dashboard.render.com/ →「New」→「Web Service」→ GitHub の `MURAMI555/kanabaa-threads` を選ぶ
2. Name：`kanabaa-threads`、Region：Singapore、Branch：main、Build Command：`pip install -r requirements.txt`、Start Command：`gunicorn app:app`、Plan：Free
3. Environment Variables に入れる：
   - `THREADS_APP_ID`＝手順2のアプリID
   - `THREADS_APP_SECRET`＝手順2の app secret
   - `IMG_BASE`＝`https://raw.githubusercontent.com/MURAMI555/kanabaa-threads/main/img`
   - `PYTHON_VERSION`＝`3.12.7`
   - （あとで）`THREADS_ACCESS_TOKEN`＝手順4で出るトークン
   - （任意・自動更新を全部任せるなら）`RENDER_API_KEY`（Render の Account Settings → API Keys）と `RENDER_SERVICE_ID`（サービスのURLの `srv-…`）
4. Deploy。終わったら `https://kanabaa-threads.onrender.com/health` を開いて `ok` が出ればよい

### 4. トークンを取る（最初の1回）

1. PC の Chrome で Threads に **kanabaa.yoru** でログインしておく
2. `https://kanabaa-threads.onrender.com/oauth/start` を開く → Threads の許可画面で「許可」
3. 画面に「長期トークン（60日）」が出る → コピーして Render の環境変数 `THREADS_ACCESS_TOKEN` に貼って保存（再デプロイされる）
   `RENDER_API_KEY` を入れてあれば自動で保存される
4. `https://kanabaa-threads.onrender.com/check` を開いて、`username` が `kanabaa.yoru` と出れば接続OK

### 5. 寝かせない（UptimeRobot）

Render の Free は15分ほど放っておくと眠り、眠っている間は投稿が出ない。
1. https://uptimerobot.com/ で無料登録
2. 「New Monitor」→ HTTP(s)、URL：`https://kanabaa-threads.onrender.com/health`、間隔 5分 → 作成

## 毎週の運用（Claude がやる）

- 次の週の投稿を `schedule.py` に足し、線画を `img/` に入れて push（Render が自動で再デプロイ）
- `/status` で投稿結果を確認。失敗があれば直す
- 文面は `.claude/skills/kanabaa` の決まり（婆さん／あんた／〜だがね1回／断定・煽り無し）。push の前に禁止語チェック

## 困ったとき

- `/check` にエラー → トークン切れ。手順4をもう一度
- 投稿が出ない → `/status` の `log` を見る。`configured: false` なら `THREADS_ACCESS_TOKEN` が入っていない。UptimeRobot が止まっていないかも見る
- 画像つきだけ失敗 → `IMG_BASE` のURLをブラウザで開いて画像が見えるか確かめる（リポジトリが Private だと見えない）

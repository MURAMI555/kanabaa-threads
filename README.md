# 叶ばぁ Threads 自動投稿（kanabaa-threads）

叶ばぁ（Threads @kanabaa.yoru）の投稿を、Render 上の小さなアプリから Threads 公式API で予定どおり自動で出す。
予定表は `schedule.py`（日本時間・1枠＝本体＋返信でつなぐ 1/3・2/3・3/3）。線画は `img/`（GitHub の raw URL で Threads に渡す）。
返信・DM は本部ルールどおり自動化しない（人が返す）。

- 5分おきに予定表を見て、時間が来た枠を投稿（30分以内の遅れなら出す）
- 二重投稿防止：投稿済みの記憶 ＋ Threads 上の直近投稿と本文の先頭を照合
- 長期トークン（60日）は毎週月曜に自動更新。`RENDER_API_KEY` と `RENDER_SERVICE_ID` があれば Render の環境変数も書き換える
- `/health` 生存確認（UptimeRobot 用）／`/status` 予定と結果／`/check` 接続確認（投稿しない）／`/oauth/start` トークン取得

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

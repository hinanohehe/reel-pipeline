# Reel Pipeline — Local Setup Guide
# Reel Pipeline — ローカル環境セットアップガイド

---

## English

### What this tool does

Paste a YouTube URL and the pipeline automatically:
1. Downloads the video
2. Transcribes the audio with Whisper (runs locally, free)
3. Asks Claude to identify the best highlight segments
4. Cuts each segment into a vertical (9:16) clip with ffmpeg
5. Uploads the clips to Google Drive
6. Creates a page in Notion

---

### Prerequisites

| Tool | Required version | Check |
|------|-----------------|-------|
| macOS | Any recent version | — |
| Python | 3.11 or newer | `python3 --version` |
| Homebrew | Any | `brew --version` |
| ffmpeg | Any | `ffmpeg -version` |

**Install Homebrew** (if not already installed):
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Install ffmpeg** via Homebrew:
```bash
brew install ffmpeg
```

**Install Python 3.11+** via Homebrew (if your version is older):
```bash
brew install python@3.11
```

---

### Step 1 — Get the project files

Ask a team member who already has the project set up to share:
- The entire `reel-pipeline/` folder, **or**
- Access to the GitHub repository + the credentials file separately (see Step 3)

Place the folder anywhere on your Mac, e.g. `~/Desktop/reel-pipeline/`.

---

### Step 2 — Create a virtual environment and install dependencies

Open **Terminal** and run:

```bash
cd ~/Desktop/reel-pipeline

# Create a virtual environment
python3 -m venv .venv

# Activate it (you must do this every time you open a new Terminal)
source .venv/bin/activate

# Install all Python packages
pip install -r requirements.txt
```

> The first `pip install` will take several minutes because it downloads PyTorch (needed by Whisper).

---

### Step 3 — Add the Google credentials file

The file is named:
```
reel-pipeline-long-to-short-09fde08f8e97.json
```

Get this file from your team admin and place it directly inside the `reel-pipeline/` folder (same level as `reel_pipeline.py`).

> **Never share or commit this file.** It is already excluded from git via `.gitignore`.

---

### Step 4 — Create the `.env.local` file

Inside the `reel-pipeline/` folder, create a file named **`.env.local`** (note the leading dot) with the following content:

```
ANTHROPIC_API_KEY=sk-ant-api03-...
NOTION_API_KEY=ntn_...
NOTION_DATABASE_ID=349be2d229bf80f2a51cf2b5fb0dc32c
NOTION_LONG_FORM_DB_ID=200be2d229bf80ee82f0db858480275c
GOOGLE_DRIVE_PARENT_FOLDER_ID=0AMq3PXoUbdgmUk9PVA
```

Replace the `ANTHROPIC_API_KEY` and `NOTION_API_KEY` values with your own keys. The database IDs and Drive folder ID are shared across the team — ask your admin for the correct values if the ones above no longer work.

**Where to get each key:**

| Key | Where to find it |
|-----|-----------------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API Keys |
| `NOTION_API_KEY` | [notion.so/my-integrations](https://www.notion.so/my-integrations) → your integration → Secret |
| `NOTION_DATABASE_ID` | Open the "Long → Short" Notion database → copy the 32-char ID from the URL |
| `NOTION_LONG_FORM_DB_ID` | Open the "Long-form videos" Notion database → copy the 32-char ID from the URL |
| `GOOGLE_DRIVE_PARENT_FOLDER_ID` | Open the shared Google Drive folder → copy the ID from the URL |

> **Never commit `.env.local` to git.** It is already excluded via `.gitignore`.

---

### Step 5 — Run the pipeline

Make sure your virtual environment is active (you should see `(.venv)` at the start of your terminal prompt):

```bash
source .venv/bin/activate   # skip if already active
cd ~/Desktop/reel-pipeline
```

Run with a YouTube URL:
```bash
python reel_pipeline.py https://www.youtube.com/watch?v=VIDEO_ID
```

**Optional flags:**

| Flag | Options | Default | Effect |
|------|---------|---------|--------|
| `--model` | `tiny` `base` `small` `medium` `large` | `base` | Whisper accuracy. `small` is a good balance. |
| `--output-dir` | any path | `./reels_output` | Where to save the clips locally |

Examples:
```bash
# Higher accuracy transcription
python reel_pipeline.py https://youtu.be/abc123 --model small

# Save clips to Desktop
python reel_pipeline.py https://youtu.be/abc123 --output-dir ~/Desktop/my_clips
```

**Expected output:**
```
Reel Pipeline  |  https://www.youtube.com/watch?v=...
Output dir     |  /Users/you/Desktop/reel-pipeline/reels_output

[1/5] Downloading video...
  Done: My Video Title

[2/5] Transcribing with Whisper...
  Done: 842s of audio transcribed

[3/5] Analysing transcript with Claude...
  Found 4 reel-worthy segment(s):
    1. [45s – 102s]  Great opening hook  (57s)
    ...

[4/5] Cutting clips with ffmpeg...
  clip_01_Great_opening_hook.mp4  (18.3 MB)
  ...

[5/5] Uploading to Google Drive & Notion...
  Drive folder: https://drive.google.com/...
  Notion page:  https://www.notion.so/...

Done. 4 clips saved to reels_output/
```

---

### Troubleshooting

**`ffmpeg: command not found`**
```bash
brew install ffmpeg
```

**`python3: command not found` or wrong version**
```bash
brew install python@3.11
# Then use python3.11 instead of python3
```

**`ModuleNotFoundError: No module named 'anthropic'` (or similar)**

Your virtual environment is not active. Run:
```bash
source .venv/bin/activate
```

**`Error: Missing required environment variables`**

Your `.env.local` file is missing or has a typo. Double-check:
- The file is named `.env.local` (starts with a dot)
- It is inside the `reel-pipeline/` folder
- There are no extra spaces around the `=` signs

**`Error: 'reel-pipeline-long-to-short-09fde08f8e97.json' not found`**

The Google credentials file is missing. Ask your team admin for this file and place it in the `reel-pipeline/` folder.

**`ERROR: unable to download video data: HTTP Error 403: Forbidden`**

This only happens when running from a cloud server (e.g. Streamlit Cloud). Running locally on your Mac should always work fine.

**The first run is slow**

Whisper downloads its model file (~150 MB for `base`) on first use. Subsequent runs are fast.

**Clips look letterboxed (black bars on top and bottom)**

This is intentional. The pipeline converts any video to 9:16 vertical format for Instagram Reels by adding black bars (letterbox), so no content is cropped.

---

---

## 日本語

### このツールでできること

YouTube URL を貼るだけで、パイプラインが自動で以下を実行します：
1. 動画をダウンロード
2. Whisper で音声を文字起こし（ローカル実行・無料）
3. Claude に見どころセグメントを分析させる
4. ffmpeg で各セグメントを縦型（9:16）クリップにカット
5. Google Drive にクリップをアップロード
6. Notion にページを作成

---

### 必要なもの

| ツール | 必要バージョン | 確認コマンド |
|--------|--------------|------------|
| macOS | 最近のバージョンであれば可 | — |
| Python | 3.11 以上 | `python3 --version` |
| Homebrew | 何でも可 | `brew --version` |
| ffmpeg | 何でも可 | `ffmpeg -version` |

**Homebrew のインストール**（まだの場合）：
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**ffmpeg のインストール**：
```bash
brew install ffmpeg
```

**Python 3.11+ のインストール**（バージョンが古い場合）：
```bash
brew install python@3.11
```

---

### Step 1 — プロジェクトファイルを入手する

すでにセットアップしているチームメンバーに以下のどちらかを共有してもらいます：
- `reel-pipeline/` フォルダ全体、**または**
- GitHub リポジトリへのアクセス権 ＋ 認証情報ファイル（Step 3 参照）

フォルダは Mac のどこにでも置いて構いません。例：`~/Desktop/reel-pipeline/`

---

### Step 2 — 仮想環境を作成して依存パッケージをインストール

**ターミナル**を開いて以下を実行します：

```bash
cd ~/Desktop/reel-pipeline

# 仮想環境を作成
python3 -m venv .venv

# 仮想環境を有効化（ターミナルを開くたびに必要）
source .venv/bin/activate

# パッケージをインストール
pip install -r requirements.txt
```

> 初回の `pip install` は PyTorch（Whisper が必要）のダウンロードのため数分かかります。

---

### Step 3 — Google 認証情報ファイルを配置する

ファイル名：
```
reel-pipeline-long-to-short-09fde08f8e97.json
```

チーム管理者からこのファイルを受け取り、`reel-pipeline/` フォルダの直下（`reel_pipeline.py` と同じ場所）に置いてください。

> **このファイルは絶対に共有・コミットしないでください。** `.gitignore` で除外済みです。

---

### Step 4 — `.env.local` ファイルを作成する

`reel-pipeline/` フォルダの中に **`.env.local`**（ドットから始まるファイル名）を作成し、以下の内容を書き込みます：

```
ANTHROPIC_API_KEY=sk-ant-api03-...
NOTION_API_KEY=ntn_...
NOTION_DATABASE_ID=349be2d229bf80f2a51cf2b5fb0dc32c
NOTION_LONG_FORM_DB_ID=200be2d229bf80ee82f0db858480275c
GOOGLE_DRIVE_PARENT_FOLDER_ID=0AMq3PXoUbdgmUk9PVA
```

`ANTHROPIC_API_KEY` と `NOTION_API_KEY` は自分のキーに置き換えてください。データベース ID と Drive フォルダ ID はチーム共通です（上の値が使えない場合は管理者に確認）。

**各キーの取得場所：**

| キー | 取得場所 |
|-----|---------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API Keys |
| `NOTION_API_KEY` | [notion.so/my-integrations](https://www.notion.so/my-integrations) → インテグレーション → シークレット |
| `NOTION_DATABASE_ID` | Notion の「Long → Short」データベースを開き、URL から 32 文字の ID をコピー |
| `NOTION_LONG_FORM_DB_ID` | Notion の「Long-form videos」データベースを開き、URL から 32 文字の ID をコピー |
| `GOOGLE_DRIVE_PARENT_FOLDER_ID` | 共有 Google Drive フォルダを開き、URL からフォルダ ID をコピー |

> **`.env.local` は絶対にコミットしないでください。** `.gitignore` で除外済みです。

---

### Step 5 — パイプラインを実行する

仮想環境が有効になっているか確認します（ターミナルのプロンプトに `(.venv)` が表示されているはずです）：

```bash
source .venv/bin/activate   # すでに有効なら不要
cd ~/Desktop/reel-pipeline
```

YouTube URL を指定して実行：
```bash
python reel_pipeline.py https://www.youtube.com/watch?v=VIDEO_ID
```

**オプション：**

| フラグ | 選択肢 | デフォルト | 効果 |
|--------|-------|----------|------|
| `--model` | `tiny` `base` `small` `medium` `large` | `base` | Whisper の精度。`small` がバランス良し |
| `--output-dir` | 任意のパス | `./reels_output` | クリップのローカル保存先 |

例：
```bash
# 精度を上げて文字起こし
python reel_pipeline.py https://youtu.be/abc123 --model small

# デスクトップに保存
python reel_pipeline.py https://youtu.be/abc123 --output-dir ~/Desktop/my_clips
```

**実行時の表示例：**
```
Reel Pipeline  |  https://www.youtube.com/watch?v=...
Output dir     |  /Users/you/Desktop/reel-pipeline/reels_output

[1/5] Downloading video...
  Done: 動画タイトル

[2/5] Transcribing with Whisper...
  Done: 842s of audio transcribed

[3/5] Analysing transcript with Claude...
  Found 4 reel-worthy segment(s):
    1. [45s – 102s]  見どころ1  (57s)
    ...

[4/5] Cutting clips with ffmpeg...
  clip_01_...mp4  (18.3 MB)
  ...

[5/5] Uploading to Google Drive & Notion...
  Drive folder: https://drive.google.com/...
  Notion page:  https://www.notion.so/...

Done. 4 clips saved to reels_output/
```

---

### トラブルシューティング

**`ffmpeg: command not found`**
```bash
brew install ffmpeg
```

**`python3: command not found` またはバージョンが古い**
```bash
brew install python@3.11
# その後は python3 の代わりに python3.11 を使う
```

**`ModuleNotFoundError: No module named 'anthropic'`（またはほかのモジュール）**

仮想環境が有効になっていません。以下を実行：
```bash
source .venv/bin/activate
```

**`Error: Missing required environment variables`**

`.env.local` ファイルがないか、内容に誤りがあります。以下を確認：
- ファイル名が `.env.local`（ドット始まり）になっているか
- `reel-pipeline/` フォルダの中に置かれているか
- `=` の前後に余分なスペースがないか

**`Error: 'reel-pipeline-long-to-short-09fde08f8e97.json' not found`**

Google 認証情報ファイルがありません。チーム管理者にファイルをもらい、`reel-pipeline/` フォルダに置いてください。

**`ERROR: HTTP Error 403: Forbidden`**

クラウドサーバー（Streamlit Cloud など）から実行した場合のみ発生します。Mac ローカルで実行する場合は問題ありません。

**初回実行が遅い**

Whisper が初回起動時にモデルファイル（`base` で約 150 MB）をダウンロードします。2 回目以降は高速です。

**クリップに黒帯が入る**

意図した動作です。Instagram リール用に動画を 9:16 縦型フォーマットに変換する際、クロップではなくレターボックス（黒帯）を使うことで内容が切れません。

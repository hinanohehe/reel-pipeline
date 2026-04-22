# reel_pipeline.py

Paste a YouTube URL → get Instagram-ready Reel clips uploaded to Google Drive and documented in Notion. Automatically.

---

## English

### What it does

1. **Downloads** the YouTube video (best-quality mp4 via yt-dlp)
2. **Transcribes** audio with OpenAI Whisper (timestamped)
3. **Analyses** the transcript with Claude (claude-sonnet-4-20250514) and identifies 2–5 reel-worthy segments (30–60 s each, high educational value / "aha moment" hooks)
4. **Cuts** each segment with ffmpeg — applies a centre 9:16 crop when the source is landscape
5. **Uploads** all clips to a Google Drive folder named after the video
6. **Creates a Notion page** with clip titles, timestamps, reasons, and hook-line suggestions

### Requirements

- Python 3.11+
- ffmpeg installed as a system package
- A Google service-account credentials file (`credentials.json`)
- API keys for Anthropic, Notion, and Google Drive

### Installation

```bash
# 1. Install ffmpeg
#    macOS
brew install ffmpeg
#    Ubuntu/Debian
sudo apt install ffmpeg

# 2. Clone / copy the project files into a folder, then:
cd your-project-folder

# 3. Create and activate a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 4. Install Python dependencies
pip install -r requirements.txt
```

> **Note on torch:** `openai-whisper` installs PyTorch automatically. The first `pip install` may download several GB. Use `--model tiny` if you want a fast, lightweight transcription.

### Configuration

#### 1. Create a `.env` file

```
ANTHROPIC_API_KEY=sk-ant-...
NOTION_API_KEY=secret_...
NOTION_DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GOOGLE_DRIVE_PARENT_FOLDER_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

#### 2. Set up Google Drive (service account)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create or select a project
2. Enable **Google Drive API**
3. Create a **Service Account** (IAM & Admin → Service Accounts → Create)
4. Download the JSON key → rename it `credentials.json` → place it next to `reel_pipeline.py`
5. In Google Drive, open the parent folder you want clips uploaded to, copy its ID from the URL (`https://drive.google.com/drive/folders/<ID>`)
6. Share that folder with the service-account email (`...@....iam.gserviceaccount.com`) as **Editor**

#### 3. Set up Notion

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) → New Integration
2. Copy the **Internal Integration Token** → paste it as `NOTION_API_KEY`
3. Open the Notion database where pages will be created, click **Share → Invite** → find your integration
4. Copy the database ID from the URL: `https://notion.so/<workspace>/<DATABASE_ID>?...`

> **Tip:** The database must have a title property (Notion calls it "Name" by default). The script tries common names automatically.

### Usage

```bash
# Basic usage
python reel_pipeline.py https://www.youtube.com/watch?v=VIDEO_ID

# Use a more accurate Whisper model (slower)
python reel_pipeline.py https://youtu.be/VIDEO_ID --model small

# Save clips to a custom folder
python reel_pipeline.py https://youtu.be/VIDEO_ID --output-dir ~/Desktop/reels

# Combine options
python reel_pipeline.py https://youtu.be/VIDEO_ID --model medium --output-dir ./my_reels
```

### Whisper model guide

| Model  | VRAM  | Speed  | Accuracy |
|--------|-------|--------|----------|
| tiny   | ~1 GB | Fastest | Lower   |
| base   | ~1 GB | Fast    | Good (default) |
| small  | ~2 GB | Medium  | Better  |
| medium | ~5 GB | Slow    | High    |
| large  | ~10 GB| Slowest | Best    |

### Terminal output when done

```
✅ 3 clip(s) created
📁 Google Drive folder: https://drive.google.com/drive/folders/...
📝 Notion page: https://notion.so/...
```

### Error handling

| Situation | Behaviour |
|-----------|-----------|
| Invalid YouTube URL | Exits with a clear message before downloading |
| yt-dlp download fails | Exits with the yt-dlp error |
| No segments identified | Exits and suggests a longer video or better Whisper model |
| Google Drive upload fails | Prints warning; Notion page is still attempted |
| Notion creation fails | Prints warning; Drive link is still printed |

---

## 日本語

### 概要

YouTubeのURLを貼るだけで、Instagramリール用の縦型クリップを自動生成します。

**処理の流れ：**
1. **ダウンロード** — yt-dlp で最高画質のmp4を取得
2. **文字起こし** — OpenAI Whisper でタイムスタンプ付きトランスクリプト生成
3. **分析** — Claude (claude-sonnet-4-20250514) で30〜60秒の「バズりやすい」セグメントを2〜5個特定
4. **カット** — ffmpeg でクリップを切り出し（横動画は9:16にトリミング）
5. **アップロード** — Google Driveに動画タイトル名のフォルダを作成してアップロード
6. **Notionページ作成** — クリップ情報・タイムスタンプ・フック文をまとめたページを自動生成

### 必要なもの

- Python 3.11以上
- ffmpeg（システムパッケージ）
- Googleサービスアカウントの認証情報ファイル（`credentials.json`）
- Anthropic / Notion / Google Drive の各APIキー

### インストール

```bash
# 1. ffmpeをインストール
#    macOS
brew install ffmpeg
#    Ubuntu/Debian
sudo apt install ffmpeg

# 2. プロジェクトフォルダへ移動
cd your-project-folder

# 3. 仮想環境を作成・有効化（推奨）
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 4. Pythonライブラリをインストール
pip install -r requirements.txt
```

> **補足：** `openai-whisper` は PyTorch を自動でインストールします。初回は数GBのダウンロードが発生することがあります。手軽に試したい場合は `--model tiny` を使ってください。

### 設定

#### 1. `.env` ファイルを作成

スクリプトと同じフォルダに `.env` という名前のファイルを作成し、以下を記入してください：

```
ANTHROPIC_API_KEY=sk-ant-...
NOTION_API_KEY=secret_...
NOTION_DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GOOGLE_DRIVE_PARENT_FOLDER_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

#### 2. Google Drive の設定（サービスアカウント）

1. [Google Cloud Console](https://console.cloud.google.com/) → プロジェクトを作成または選択
2. **Google Drive API** を有効化
3. **サービスアカウント**を作成（IAMと管理 → サービスアカウント → 作成）
4. JSONキーをダウンロード → `credentials.json` にリネーム → スクリプトと同じフォルダに配置
5. Google Drive でアップロード先のフォルダを開き、URLからID（`https://drive.google.com/drive/folders/<ID>` の部分）をコピー
6. そのフォルダをサービスアカウントのメールアドレス（`...@....iam.gserviceaccount.com`）と**編集者**として共有

#### 3. Notion の設定

1. [notion.so/my-integrations](https://www.notion.so/my-integrations) → 「新しいインテグレーション」
2. **インターナルインテグレーショントークン**をコピー → `NOTION_API_KEY` に貼り付け
3. クリップ情報を保存したいNotionデータベースを開き、「共有」→「招待」→ インテグレーションを追加
4. URLからデータベースIDをコピー：`https://notion.so/<workspace>/<DATABASE_ID>?...`

### 使い方

```bash
# 基本的な使い方
python reel_pipeline.py https://www.youtube.com/watch?v=VIDEO_ID

# 精度の高いWhisperモデルを使用（処理時間が長くなります）
python reel_pipeline.py https://youtu.be/VIDEO_ID --model small

# クリップの保存先を指定
python reel_pipeline.py https://youtu.be/VIDEO_ID --output-dir ~/Desktop/reels

# オプションの組み合わせ
python reel_pipeline.py https://youtu.be/VIDEO_ID --model medium --output-dir ./my_reels
```

### 完了時のターミナル表示例

```
✅ 3 clip(s) created
📁 Google Drive folder: https://drive.google.com/drive/folders/...
📝 Notion page: https://notion.so/...
```

### よくあるエラーと対処法

| 状況 | 動作 |
|------|------|
| 無効なYouTube URL | ダウンロード前にエラーメッセージを表示して終了 |
| yt-dlpのダウンロード失敗 | yt-dlpのエラーを表示して終了 |
| セグメントが見つからない | エラーメッセージを表示（長い動画や精度の高いWhisperモデルの使用を提案） |
| Google Driveのアップロード失敗 | 警告を表示し、Notionページ作成は続行 |
| Notionページ作成失敗 | 警告を表示し、Driveリンクは表示される |

---

## Project structure

```
.
├── reel_pipeline.py       # Main script
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── .env                   # API keys (create this — do NOT commit to git)
├── credentials.json       # Google service-account key (do NOT commit to git)
└── reels_output/          # Output clips (created automatically)
    ├── clip_01_Title.mp4
    ├── clip_02_Title.mp4
    └── ...
```

> **Security:** Add `.env` and `credentials.json` to your `.gitignore` — never commit API keys or service-account credentials.

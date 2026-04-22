"""
app.py — Reel Pipeline Web App
Streamlit frontend for the YouTube → Instagram Reels pipeline.
"""

import os
import sys
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# ── Load env ───────────────────────────────────────────────────────────────────
# Streamlit Cloud uses st.secrets; local dev uses .env.local
if not os.getenv("ANTHROPIC_API_KEY"):
    load_dotenv(".env.local")

# Inject Streamlit secrets into env (for Streamlit Cloud deployment)
for key in [
    "ANTHROPIC_API_KEY", "NOTION_API_KEY", "NOTION_DATABASE_ID",
    "NOTION_LONG_FORM_DB_ID", "GOOGLE_DRIVE_PARENT_FOLDER_ID",
]:
    if key in st.secrets and not os.getenv(key):
        os.environ[key] = st.secrets[key]

# Write credentials.json from secrets if present (Streamlit Cloud)
if "GOOGLE_CREDENTIALS_JSON" in st.secrets and not Path("credentials.json").exists():
    import json
    creds = dict(st.secrets["GOOGLE_CREDENTIALS_JSON"])
    Path("credentials.json").write_text(json.dumps(creds))

# ── Import pipeline (after env is set) ────────────────────────────────────────
from reel_pipeline import (
    validate_youtube_url,
    download_video,
    transcribe_video,
    analyze_with_claude,
    cut_clip,
    upload_to_google_drive,
    create_notion_page,
    sanitize_name,
)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Reel Pipeline",
    page_icon="🎬",
    layout="centered",
)

# ── Notion DB link ─────────────────────────────────────────────────────────────
db_id = os.getenv("NOTION_DATABASE_ID", "").replace("-", "")
NOTION_DB_URL = f"https://www.notion.so/{db_id}" if db_id else ""

# ── Header ─────────────────────────────────────────────────────────────────────
col_title, col_notion = st.columns([4, 1])
with col_title:
    st.title("🎬 Reel Pipeline")
with col_notion:
    if NOTION_DB_URL:
        st.link_button("📋 Notion DB", NOTION_DB_URL, use_container_width=True)

st.markdown(
    "YouTubeのURLを貼るだけで、Instagramリール用クリップを自動生成します。  \n"
    "クリップはGoogle DriveにアップロードされNotionに記録されます。"
)
st.divider()

# ── Input ──────────────────────────────────────────────────────────────────────
url = st.text_input(
    "YouTube URL",
    placeholder="https://www.youtube.com/watch?v=...",
)

with st.expander("⚙️ 詳細設定（任意）"):
    model = st.select_slider(
        "Whisper文字起こし精度",
        options=["tiny", "base", "small", "medium"],
        value="base",
        help="右に行くほど精度が高いが処理時間が増えます",
    )
    output_dir_input = st.text_input(
        "ローカル出力フォルダ",
        value="./reels_output",
        help="クリップの一時保存先",
    )

st.divider()
run = st.button(
    "▶ リールを生成する",
    type="primary",
    use_container_width=True,
    disabled=not url.strip(),
)

# ── Pipeline ───────────────────────────────────────────────────────────────────
if run:
    url = url.strip()

    if not validate_youtube_url(url):
        st.error("有効なYouTube URLを入力してください。")
        st.stop()

    output_dir = Path(output_dir_input)
    output_dir.mkdir(parents=True, exist_ok=True)

    progress_bar = st.progress(0, text="準備中...")
    log = st.empty()

    folder_link = ""
    notion_url = ""
    clips = []

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            # 1. Download
            progress_bar.progress(5, text="📥 動画をダウンロード中...")
            video_path, video_title = download_video(url, tmp_dir)
            log.caption(f"動画: {video_title}")

            # 2. Transcribe
            progress_bar.progress(20, text=f"📝 文字起こし中... ({model}モデル)")
            transcript, duration = transcribe_video(video_path, model)
            log.caption(f"動画: {video_title}　|　音声: {duration:.0f}秒")

            # 3. Analyze
            progress_bar.progress(45, text="🤖 Claudeが見どころを分析中...")
            segments = analyze_with_claude(transcript, video_title, duration)
            log.caption(
                f"動画: {video_title}　|　音声: {duration:.0f}秒　|　"
                f"セグメント: {len(segments)}個"
            )

            # 4. Cut clips
            progress_bar.progress(60, text="✂️ クリップをカット中...")
            for i, seg in enumerate(segments, 1):
                safe = sanitize_name(seg["title"]).replace(" ", "_")
                filename = f"clip_{i:02d}_{safe}.mp4"
                out_path = output_dir / filename
                cut_clip(video_path, seg, out_path, duration)
                clips.append({**seg, "filename": filename, "path": str(out_path)})
                progress_bar.progress(
                    60 + int(10 * i / len(segments)),
                    text=f"✂️ クリップ {i}/{len(segments)} をカット中...",
                )

            # 5a. Drive upload
            progress_bar.progress(75, text="☁️ Google Driveにアップロード中...")
            try:
                folder_link, _ = upload_to_google_drive(clips, video_title)
            except Exception as exc:
                st.warning(f"Google Driveアップロード失敗: {exc}")
                folder_link = ""

            # 5b. Notion page
            progress_bar.progress(90, text="📓 Notionページを作成中...")
            try:
                notion_url = create_notion_page(video_title, clips, folder_link, url)
            except Exception as exc:
                st.warning(f"Notionページ作成失敗: {exc}")
                notion_url = ""

            progress_bar.progress(100, text="✅ 完了！")
            log.empty()

    except Exception as exc:
        progress_bar.empty()
        st.error(f"エラーが発生しました: {exc}")
        st.stop()

    # ── Results ────────────────────────────────────────────────────────────────
    st.success(f"✅ {len(clips)}クリップ作成完了！")

    col_drive, col_notion = st.columns(2)
    with col_drive:
        if folder_link:
            st.link_button(
                "📁 Google Driveで開く", folder_link, use_container_width=True
            )
        else:
            st.button("📁 Google Drive (失敗)", disabled=True, use_container_width=True)
    with col_notion:
        if notion_url:
            st.link_button(
                "📝 Notionページを開く", notion_url, use_container_width=True
            )
        else:
            st.button("📝 Notion (失敗)", disabled=True, use_container_width=True)

    st.divider()
    st.subheader("作成されたクリップ")
    for i, clip in enumerate(clips, 1):
        s, e = int(clip["start"]), int(clip["end"])
        timestamp = f"{s // 60:02d}:{s % 60:02d} → {e // 60:02d}:{e % 60:02d}"
        dur = int(clip["end"] - clip["start"])
        with st.container(border=True):
            st.markdown(f"**{i}. {clip['title']}**")
            st.caption(f"⏱ {timestamp}（{dur}秒） | 🎣 {clip['hook_line']}")
            st.write(clip["reason"])

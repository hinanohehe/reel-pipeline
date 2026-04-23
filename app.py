"""
app.py — Reel Pipeline Web App
Streamlit frontend for the YouTube → Instagram Reels pipeline.
"""

import os
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# ── Load env ───────────────────────────────────────────────────────────────────
if not os.getenv("ANTHROPIC_API_KEY"):
    load_dotenv(".env.local")

for key in [
    "ANTHROPIC_API_KEY", "NOTION_API_KEY", "NOTION_DATABASE_ID",
    "NOTION_LONG_FORM_DB_ID", "GOOGLE_DRIVE_PARENT_FOLDER_ID",
]:
    if key in st.secrets and not os.getenv(key):
        os.environ[key] = st.secrets[key]

if "GOOGLE_CREDENTIALS_JSON_B64" in st.secrets and not Path("credentials.json").exists():
    import base64
    decoded = base64.b64decode(st.secrets["GOOGLE_CREDENTIALS_JSON_B64"]).decode()
    Path("credentials.json").write_text(decoded)

# ── Import pipeline ────────────────────────────────────────────────────────────
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
    "Paste a YouTube URL to automatically generate Instagram Reel clips.  \n"
    "Clips are uploaded to Google Drive and logged in Notion."
)
st.divider()

# ── Input ──────────────────────────────────────────────────────────────────────
url = st.text_input(
    "YouTube URL",
    placeholder="https://www.youtube.com/watch?v=...",
)

run = st.button(
    "Generate Reels",
    type="primary",
    use_container_width=True,
    disabled=not url.strip(),
)

# ── Pipeline ───────────────────────────────────────────────────────────────────
if run:
    url = url.strip()

    if not validate_youtube_url(url):
        st.error("Please enter a valid YouTube URL.")
        st.stop()

    progress_bar = st.progress(0, text="Preparing...")
    log = st.empty()

    folder_link = ""
    notion_url = ""
    clips = []

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            output_dir = tmp_dir / "clips"
            output_dir.mkdir()

            # 1. Download
            progress_bar.progress(5, text="Downloading video...")
            video_path, video_title = download_video(url, tmp_dir)
            log.caption(f"Video: {video_title}")

            # 2. Transcribe
            progress_bar.progress(20, text="Transcribing audio...")
            transcript, duration = transcribe_video(video_path, "base")
            log.caption(f"Video: {video_title}  |  Duration: {duration:.0f}s")

            # 3. Analyze
            progress_bar.progress(45, text="Analyzing highlights with Claude...")
            segments = analyze_with_claude(transcript, video_title, duration)
            log.caption(
                f"Video: {video_title}  |  Duration: {duration:.0f}s  |  "
                f"Segments: {len(segments)}"
            )

            # 4. Cut clips
            progress_bar.progress(60, text="Cutting clips...")
            clip_bytes = {}
            for i, seg in enumerate(segments, 1):
                safe = sanitize_name(seg["title"]).replace(" ", "_")
                filename = f"clip_{i:02d}_{safe}.mp4"
                out_path = output_dir / filename
                cut_clip(video_path, seg, out_path, duration)
                clips.append({**seg, "filename": filename, "path": str(out_path)})
                clip_bytes[filename] = out_path.read_bytes()
                progress_bar.progress(
                    60 + int(10 * i / len(segments)),
                    text=f"Cutting clip {i}/{len(segments)}...",
                )

            # 5a. Drive upload
            progress_bar.progress(75, text="Uploading to Google Drive...")
            try:
                folder_link, _ = upload_to_google_drive(clips, video_title)
            except Exception as exc:
                st.warning(f"Google Drive upload failed: {exc}")
                folder_link = ""

            # 5b. Notion page
            progress_bar.progress(90, text="Creating Notion page...")
            try:
                notion_url = create_notion_page(video_title, clips, folder_link, url)
            except Exception as exc:
                st.warning(f"Notion page creation failed: {exc}")
                notion_url = ""

            progress_bar.progress(100, text="Done!")
            log.empty()

    except Exception as exc:
        progress_bar.empty()
        st.error(f"Error: {exc}")
        st.stop()

    # ── Results ────────────────────────────────────────────────────────────────
    st.success(f"{len(clips)} clips created successfully!")

    col_drive, col_notion = st.columns(2)
    with col_drive:
        if folder_link:
            st.link_button("Open Google Drive", folder_link, use_container_width=True)
        else:
            st.button("Google Drive (failed)", disabled=True, use_container_width=True)
    with col_notion:
        if notion_url:
            st.link_button("Open Notion Page", notion_url, use_container_width=True)
        else:
            st.button("Notion (failed)", disabled=True, use_container_width=True)

    st.divider()
    st.subheader("Generated Clips")
    for i, clip in enumerate(clips, 1):
        s, e = int(clip["start"]), int(clip["end"])
        timestamp = f"{s // 60:02d}:{s % 60:02d} → {e // 60:02d}:{e % 60:02d}"
        dur = int(clip["end"] - clip["start"])
        with st.container(border=True):
            col_info, col_dl = st.columns([4, 1])
            with col_info:
                st.markdown(f"**{i}. {clip['title']}**")
                st.caption(f"{timestamp} ({dur}s)  |  Hook: {clip['hook_line']}")
                st.write(clip["reason"])
            with col_dl:
                filename = clip["filename"]
                if filename in clip_bytes:
                    st.download_button(
                        label="Download",
                        data=clip_bytes[filename],
                        file_name=filename,
                        mime="video/mp4",
                        use_container_width=True,
                        key=f"dl_{i}",
                    )

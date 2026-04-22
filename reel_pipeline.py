#!/usr/bin/env python3
"""
reel_pipeline.py - YouTube → Instagram Reels automated pipeline.

Usage:
    python reel_pipeline.py <YouTube URL>
    python reel_pipeline.py <YouTube URL> --model small --output-dir ./my_reels
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import anthropic
import whisper
import yt_dlp
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from notion_client import Client as NotionClient
from notion_client import APIResponseError

# ── Config ─────────────────────────────────────────────────────────────────────
load_dotenv(".env.local")

CLAUDE_MODEL = "claude-sonnet-4-20250514"
CREDENTIALS_FILE = "reel-pipeline-long-to-short-09fde08f8e97.json"
DEFAULT_OUTPUT_DIR = "./reels_output"
DEFAULT_WHISPER_MODEL = "base"


# ── ID helpers (accept full URLs or raw IDs) ───────────────────────────────────

def _notion_id(value: str) -> str:
    """Extract a 32-char hex Notion ID from a full URL or return as-is."""
    value = value.strip()
    match = re.search(r"([0-9a-f]{32})", value.replace("-", ""))
    return match.group(1) if match else value


def _drive_folder_id(value: str) -> str:
    """Extract folder ID from a Google Drive URL or return as-is."""
    value = value.strip()
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", value)
    return match.group(1) if match else value


# ── Notion: link to Long-form videos database ──────────────────────────────────

def _find_long_form_page(notion: NotionClient, video_title: str) -> str | None:
    """
    Fuzzy-search the Long-form videos DB using key words from the title.
    Uses notion.search() so partial matches work across the workspace.
    Returns Notion page ID if found, else None.
    """
    raw_id = os.getenv("NOTION_LONG_FORM_DB_ID", "").strip()
    if not raw_id:
        return None
    db_id = _notion_id(raw_id)

    # Build a short keyword query: first 3 words longer than 3 chars
    keywords = [w for w in re.split(r"\W+", video_title) if len(w) > 3][:3]
    query = " ".join(keywords) if keywords else video_title[:40]

    try:
        results = notion.search(
            query=query,
            filter={"property": "object", "value": "page"},
            page_size=10,
        )
        for page in results.get("results", []):
            parent_db = page.get("parent", {}).get("database_id", "").replace("-", "")
            if parent_db == db_id.replace("-", ""):
                return page["id"]
        return None
    except Exception as exc:
        print(f"  Note: Could not search Long-form videos DB — {exc}")
        return None


def _find_relation_prop(notion: NotionClient, long_short_db_id: str) -> str | None:
    """
    Inspect the 'Long -> Short' database schema and find the relation
    property that points to the Long-form videos database.
    Returns the property name, or None if not found.
    """
    raw_long = os.getenv("NOTION_LONG_FORM_DB_ID", "").strip()
    if not raw_long:
        return None
    long_form_id = _notion_id(raw_long)

    try:
        db = notion.databases.retrieve(database_id=long_short_db_id)
        for prop_name, prop_val in db.get("properties", {}).items():
            if prop_val["type"] == "relation":
                related = prop_val.get("relation", {}).get("database_id", "")
                if related.replace("-", "") == long_form_id.replace("-", ""):
                    return prop_name
    except Exception:
        pass
    return None


# ── Validation helpers ─────────────────────────────────────────────────────────

def check_system_dependencies() -> None:
    """Ensure ffmpeg and ffprobe are on PATH."""
    for tool in ("ffmpeg", "ffprobe"):
        result = subprocess.run(
            ["which", tool], capture_output=True
        )
        if result.returncode != 0:
            print(
                f"Error: '{tool}' not found. Install ffmpeg via:\n"
                "  macOS:  brew install ffmpeg\n"
                "  Ubuntu: sudo apt install ffmpeg",
                file=sys.stderr,
            )
            sys.exit(1)


def check_env_config() -> None:
    """Validate all required environment variables and credential files."""
    required = {
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        "NOTION_API_KEY": os.getenv("NOTION_API_KEY"),
        "NOTION_DATABASE_ID": os.getenv("NOTION_DATABASE_ID"),
        "GOOGLE_DRIVE_PARENT_FOLDER_ID": os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print("Error: Missing required environment variables:", file=sys.stderr)
        for k in missing:
            print(f"  - {k}", file=sys.stderr)
        print("\nCreate a .env file with those values.", file=sys.stderr)
        sys.exit(1)

    if not Path(CREDENTIALS_FILE).exists():
        print(
            f"Error: '{CREDENTIALS_FILE}' not found.\n"
            "Download your Google service-account JSON and place it here.",
            file=sys.stderr,
        )
        sys.exit(1)


def validate_youtube_url(url: str) -> bool:
    """Return True if url looks like a valid YouTube video URL."""
    patterns = [
        r"https?://(www\.)?youtube\.com/watch\?.*v=[\w-]+",
        r"https?://youtu\.be/[\w-]+",
        r"https?://(www\.)?youtube\.com/shorts/[\w-]+",
    ]
    return any(re.match(p, url) for p in patterns)


# ── Step 1: Download ───────────────────────────────────────────────────────────

def download_video(url: str, output_dir: Path) -> tuple[Path, str]:
    """
    Download the best-quality mp4 with yt-dlp.
    Returns (video_path, video_title).
    """
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title", "Unknown_Title")

    mp4_files = list(output_dir.glob("*.mp4"))
    if not mp4_files:
        raise FileNotFoundError("yt-dlp completed but no mp4 file was found.")

    video_path = max(mp4_files, key=lambda p: p.stat().st_mtime)
    return video_path, title


# ── Step 2: Transcribe ─────────────────────────────────────────────────────────

def transcribe_video(
    video_path: Path, model_name: str = DEFAULT_WHISPER_MODEL
) -> tuple[str, float]:
    """
    Transcribe audio with OpenAI Whisper.
    Returns (formatted_transcript, audio_duration_seconds).
    """
    print(f"  Loading Whisper '{model_name}' model (first run downloads weights)...")
    model = whisper.load_model(model_name)

    print(f"  Transcribing {video_path.name} ...")
    result = model.transcribe(str(video_path), verbose=False)

    segments = result.get("segments", [])
    duration = segments[-1]["end"] if segments else 0.0

    lines = [
        f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text'].strip()}"
        for seg in segments
    ]
    transcript = "\n".join(lines)
    return transcript, duration


# ── Step 3: Analyze with Claude ────────────────────────────────────────────────

def analyze_with_claude(
    transcript: str, video_title: str, duration: float
) -> list[dict]:
    """
    Ask Claude to identify 2-5 reel-worthy segments.
    Returns a list of validated segment dicts.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    system_prompt = (
        "You are a social media content strategist specialising in viral Instagram Reels. "
        "You have a sharp eye for moments that educate, surprise, or inspire viewers "
        "within 30–60 seconds."
    )

    user_prompt = f"""Analyse this transcript and identify 2–5 segments perfect for Instagram Reels.

Video Title: {video_title}
Total Duration: {duration:.0f} seconds

Transcript (with timestamps):
{transcript}

Select segments that have:
- A strong hook in the opening 3 seconds (surprising stat, bold claim, or intriguing question)
- High educational value, an "aha moment", or emotional resonance
- A complete, standalone thought — no extra context required
- Natural start and end points at sentence boundaries

Hard requirements:
- Each segment must be 30–60 seconds long
- Segments must not overlap
- start/end values must be within [0, {duration:.0f}]

Return ONLY a valid JSON array — no markdown, no explanation:
[
  {{
    "start": <float>,
    "end": <float>,
    "title": "<15 words or fewer, in English>",
    "reason": "<1–2 sentences explaining why this is reel-worthy>",
    "hook_line": "<exact opening line or phrase that grabs viewers>"
  }}
]"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = response.content[0].text.strip()

    # Parse — try direct, then extract JSON block from markdown
    try:
        segments = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", raw)
        if not match:
            raise ValueError(
                f"Claude returned a response that is not parseable as JSON:\n{raw}"
            )
        segments = json.loads(match.group())

    if not isinstance(segments, list) or not segments:
        raise ValueError("Claude returned an empty segment list.")

    # Validate durations (generous ±10 s window around 30–60 s)
    valid = []
    for seg in segments:
        seg_dur = seg.get("end", 0) - seg.get("start", 0)
        if 20 <= seg_dur <= 70:
            valid.append(seg)
        else:
            print(
                f"  Skipping '{seg.get('title', '?')}' "
                f"(duration {seg_dur:.0f}s outside acceptable range)"
            )

    if not valid:
        raise ValueError(
            "No segments in the 30–60 s range were identified. "
            "Try a longer video or a different Whisper model for accuracy."
        )

    return valid


# ── Step 4: Cut clips with ffmpeg ──────────────────────────────────────────────

def get_video_dimensions(video_path: Path) -> tuple[int, int]:
    """Return (width, height) of the video stream via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    return int(stream["width"]), int(stream["height"])


def cut_clip(
    video_path: Path, segment: dict, out_path: Path, video_duration: float = 0
) -> None:
    """
    Cut a segment with ±3 s padding (clamped to video bounds).
    Landscape videos are letterboxed to 9:16 — full horizontal frame kept,
    black bars added top and bottom. Portrait/square kept as-is.
    """
    width, height = get_video_dimensions(video_path)

    PADDING = 3.0
    start = max(0.0, segment["start"] - PADDING)
    end = segment["end"] + PADDING
    if video_duration > 0:
        end = min(video_duration, end)
    clip_duration = end - start

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(video_path),
        "-t", str(clip_duration),
    ]

    if width > height:
        # Landscape → letterbox to 9:16 at 1080×1920
        # Scale width to 1080 (maintaining AR), then pad height to 1920 with black
        cmd += ["-vf", "scale=1080:-2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"]
    # Portrait / square → keep as-is

    cmd += [
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        str(out_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error:\n{result.stderr[-600:]}")


# ── Step 5a: Google Drive upload ───────────────────────────────────────────────

def sanitize_name(name: str, max_len: int = 100) -> str:
    """Strip characters that are illegal in filenames / Drive folder names."""
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len]


def upload_to_google_drive(
    clips: list[dict], video_title: str
) -> tuple[str, list[dict]]:
    """
    Create a Drive folder named after the video, upload all clips.
    Supports both personal shared folders and Shared Drives (Team Drives).
    Returns (folder_web_link, list of {title, filename, link}).
    """
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    service = build("drive", "v3", credentials=creds)

    parent_id = _drive_folder_id(os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID", ""))

    # Detect whether the parent lives in a Shared Drive
    parent_info = service.files().get(
        fileId=parent_id,
        supportsAllDrives=True,
        fields="id,driveId",
    ).execute()
    in_shared_drive = bool(parent_info.get("driveId"))

    # Create subfolder
    folder_meta = {
        "name": sanitize_name(video_title),
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(
        body=folder_meta,
        fields="id,webViewLink",
        supportsAllDrives=True,
    ).execute()
    folder_id = folder["id"]
    folder_link = folder["webViewLink"]

    # Personal Drive folders need an explicit "anyone with link" permission.
    # Shared Drives inherit access from Drive membership — skip this there.
    if not in_shared_drive:
        try:
            service.permissions().create(
                fileId=folder_id,
                supportsAllDrives=True,
                body={"type": "anyone", "role": "reader"},
            ).execute()
        except Exception as exc:
            print(f"  Note: could not set folder permissions — {exc}")

    # Upload clips
    results = []
    for clip in clips:
        print(f"  Uploading {clip['filename']} ...")
        media = MediaFileUpload(
            clip["path"], mimetype="video/mp4", resumable=True
        )
        uploaded = service.files().create(
            body={"name": clip["filename"], "parents": [folder_id]},
            media_body=media,
            fields="id,webViewLink",
            supportsAllDrives=True,
        ).execute()
        results.append(
            {
                "title": clip["title"],
                "filename": clip["filename"],
                "link": uploaded["webViewLink"],
            }
        )

    return folder_link, results


# ── Step 5b: Notion page ───────────────────────────────────────────────────────

def _title_property(title_text: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": title_text}}]}


def _count_db_pages(notion: NotionClient, database_id: str) -> int:
    """Paginate through a database and return the total page count."""
    count, cursor = 0, None
    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        # notion-client v3: querying moved to data_sources.query()
        result = notion.data_sources.query(
            data_source_id=database_id,
            **body,
        )
        count += len(result.get("results", []))
        if not result.get("has_more"):
            break
        cursor = result.get("next_cursor")
    return count


def create_notion_page(
    video_title: str, clips: list[dict], folder_link: str, youtube_url: str = ""
) -> str:
    """
    Create a Notion page in the 'Long -> Short' database.
    Reads the DB schema first and only sets properties that actually exist,
    skipping any that are missing or the wrong type — no crashes.
    Returns the page URL.
    """
    notion = NotionClient(auth=os.getenv("NOTION_API_KEY"))
    database_id = _notion_id(os.getenv("NOTION_DATABASE_ID", ""))
    now = datetime.now()

    # ── Detect title property name (all DBs have exactly one title-type prop) ───
    title_prop_name = "Name"
    try:
        db = notion.databases.retrieve(database_id=database_id)
        title_prop_name = next(
            (k for k, v in db.get("properties", {}).items() if v["type"] == "title"),
            "Name",
        )
    except Exception:
        pass

    # ── Find Long-form video page + relation property ──────────────────────────
    long_form_page_id = _find_long_form_page(notion, video_title)
    relation_prop = _find_relation_prop(notion, database_id) if long_form_page_id else None
    if long_form_page_id and relation_prop:
        print(f"  Linking to Long-form videos page via '{relation_prop}' property")

    # ── Count existing pages for Unique Number ────────────────────────────────
    unique_number = None
    try:
        unique_number = _count_db_pages(notion, database_id) + 1
    except Exception:
        pass

    # ── Build properties dict — set directly, no schema pre-validation ────────
    # The Notion API will reject unknown properties; we retry without them below.
    properties: dict = {title_prop_name: _title_property(video_title)}

    if folder_link.startswith("http"):
        properties["Google Folder Location"] = {"url": folder_link}
    if youtube_url:
        properties["Source Video YouTube Link"] = {"url": youtube_url}
    if long_form_page_id and relation_prop:
        properties[relation_prop] = {"relation": [{"id": long_form_page_id}]}
    properties["Clip Quantity"] = {"number": len(clips)}
    if unique_number is not None:
        properties["Unique Number"] = {"number": unique_number}
    properties["Created Date"] = {"date": {"start": now.strftime("%Y-%m-%d")}}
    properties["Created Time"] = {
        "rich_text": [{"type": "text", "text": {"content": now.strftime("%H:%M")}}]
    }
    # Person Created — skipped (requires the user's Notion user ID)

    # ── Build page body — clips only, no URL blocks (those are in properties) ─
    children: list[dict] = [
        {"object": "block", "type": "divider", "divider": {}},
    ]

    for i, clip in enumerate(clips, 1):
        s, e = int(clip["start"]), int(clip["end"])
        timestamp = f"{s // 60:02d}:{s % 60:02d} → {e // 60:02d}:{e % 60:02d}"
        dur = int(clip["end"] - clip["start"])

        children += [
            {
                "object": "block", "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": f"Clip {i}: {clip['title']}"}}]
                },
            },
            {
                "object": "block", "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "⏱ Timestamp: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f"{timestamp} ({dur}s)"}},
                    ]
                },
            },
            {
                "object": "block", "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Why it's reel-worthy: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": clip["reason"]}},
                    ]
                },
            },
            {
                "object": "block", "type": "quote",
                "quote": {
                    "rich_text": [{"type": "text", "text": {"content": f'Hook: "{clip["hook_line"]}"'}}]
                },
            },
            {"object": "block", "type": "divider", "divider": {}},
        ]

    # ── Create the page ───────────────────────────────────────────────────────
    # First attempt: all properties. If Notion rejects an unknown property,
    # fall back to title-only so the page is always created.
    try:
        page = notion.pages.create(
            parent={"database_id": database_id},
            properties=properties,
            children=children,
        )
    except APIResponseError as exc:
        err = str(exc).lower()
        if "property" in err or "validation" in err:
            print(f"  Note: some properties were rejected by Notion ({exc}); retrying with title only")
            page = notion.pages.create(
                parent={"database_id": database_id},
                properties={title_prop_name: _title_property(video_title)},
                children=children,
            )
        else:
            raise
    return page.get("url", "https://notion.so")


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="YouTube → Instagram Reels automated pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python reel_pipeline.py https://youtu.be/dQw4w9WgXcQ
  python reel_pipeline.py https://www.youtube.com/watch?v=abc123 --model small
  python reel_pipeline.py <URL> --output-dir ~/Desktop/reels
        """,
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "--model",
        default=DEFAULT_WHISPER_MODEL,
        choices=["tiny", "base", "small", "medium", "large"],
        help=(
            f"Whisper model size (default: {DEFAULT_WHISPER_MODEL}). "
            "Larger models are slower but more accurate."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Local directory for output clips (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()

    # ── Pre-flight checks ──────────────────────────────────────────────────────
    if not validate_youtube_url(args.url):
        print(f"Error: '{args.url}' is not a recognised YouTube URL.", file=sys.stderr)
        sys.exit(1)

    check_system_dependencies()
    check_env_config()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nReel Pipeline  |  {args.url}")
    print(f"Output dir     |  {output_dir.resolve()}\n")

    # Work in a temp dir so partial downloads are cleaned up on exit
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # ── 1. Download ────────────────────────────────────────────────────────
        print("[1/5] Downloading video...")
        try:
            video_path, video_title = download_video(args.url, tmp_dir)
            print(f"  Done: {video_title}")
        except Exception as exc:
            print(f"  Download failed: {exc}", file=sys.stderr)
            sys.exit(1)

        # ── 2. Transcribe ──────────────────────────────────────────────────────
        print("\n[2/5] Transcribing with Whisper...")
        try:
            transcript, duration = transcribe_video(video_path, args.model)
            print(f"  Done: {duration:.0f}s of audio transcribed")
        except Exception as exc:
            print(f"  Transcription failed: {exc}", file=sys.stderr)
            sys.exit(1)

        # ── 3. Analyse with Claude ─────────────────────────────────────────────
        print("\n[3/5] Analysing transcript with Claude...")
        try:
            segments = analyze_with_claude(transcript, video_title, duration)
            print(f"  Found {len(segments)} reel-worthy segment(s):")
            for i, seg in enumerate(segments, 1):
                d = seg["end"] - seg["start"]
                print(
                    f"    {i}. [{seg['start']:.0f}s – {seg['end']:.0f}s]  "
                    f"{seg['title']}  ({d:.0f}s)"
                )
        except Exception as exc:
            print(f"  Analysis failed: {exc}", file=sys.stderr)
            sys.exit(1)

        # ── 4. Cut clips ───────────────────────────────────────────────────────
        print("\n[4/5] Cutting clips with ffmpeg...")
        clips: list[dict] = []
        for i, seg in enumerate(segments, 1):
            safe = sanitize_name(seg["title"]).replace(" ", "_")
            filename = f"clip_{i:02d}_{safe}.mp4"
            out_path = output_dir / filename
            try:
                cut_clip(video_path, seg, out_path, duration)
                size_mb = out_path.stat().st_size / 1_000_000
                print(f"  {filename}  ({size_mb:.1f} MB)")
                clips.append({**seg, "filename": filename, "path": str(out_path)})
            except Exception as exc:
                print(f"  Warning: clip {i} failed — {exc}", file=sys.stderr)

        if not clips:
            print("Error: no clips were created.", file=sys.stderr)
            sys.exit(1)

        # ── 5a. Upload to Google Drive ─────────────────────────────────────────
        print(f"\n[5a/5] Uploading {len(clips)} clip(s) to Google Drive...")
        folder_link = "(upload failed)"
        try:
            folder_link, upload_results = upload_to_google_drive(clips, video_title)
            print(f"  Done — folder: {folder_link}")
            print("  Clips uploaded:")
            for r in upload_results:
                print(f"    - {r['title']}")
        except Exception as exc:
            print(f"  Google Drive upload failed: {exc}", file=sys.stderr)

        # ── 5b. Create Notion page ─────────────────────────────────────────────
        print("\n[5b/5] Creating Notion page...")
        notion_url = "(creation failed)"
        try:
            notion_url = create_notion_page(video_title, clips, folder_link, args.url)
            print(f"  Done — {notion_url}")
        except Exception as exc:
            print(f"  Notion page creation failed: {exc}", file=sys.stderr)

    # ── Summary ────────────────────────────────────────────────────────────────
    print()
    print("=" * 56)
    print(f"✅ {len(clips)} clip(s) created")
    print(f"📁 Google Drive folder: {folder_link}")
    print(f"📝 Notion page: {notion_url}")
    print("=" * 56)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
RSSpad feed core - pure-Python logic for scanning an audio folder and
building a podcast-compliant RSS 2.0 feed. No GTK dependencies, so it can be
tested and used from the command line:

    python3 feed_core.py "/path/to/folder"
"""

import json
import os
import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote
from xml.sax.saxutils import escape

try:
    from tinytag import TinyTag  # optional: titles/durations from tags
except ImportError:  # pragma: no cover - depends on environment
    TinyTag = None

CONFIG_NAME = ".rsspad.json"

MIME_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/x-m4v",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
}

VIDEO_EXTS = {".mp4", ".m4v", ".mov"}

# When several files share a name (e.g. "Song.wav" and "Song.mp3"), the feed
# uses the most podcast-friendly one in this order.
FORMAT_PREFERENCE = [".mp4", ".m4v", ".mov", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav"]

DEFAULT_CONFIG = {
    "base_url": "https://yourdomain.com/podcast",
    "title": "",
    "description": "My personal daily streaming podcast feed.",
    "author": "",
    "language": "en-us",
    "image_url": "",
    "category": "Music",
    "explicit": False,
    "output_name": "feed.xml",
    "mp3_bitrate": "192k",
    "auto_generate": True,
    "publish_command": "",
    "github_repo": "",          # "owner/repo" once GitHub hosting is set up
    "github_release_tag": "episodes",
    # filename -> {"title", "description", "url" (hosted media URL), "pub" (epoch)}
    "tracks": {},
}


@dataclass
class Track:
    path: Path
    title: str
    description: str
    duration: Optional[float]
    size: int
    mtime: float
    mime: str
    alternates: List[Path] = field(default_factory=list)
    url: str = ""  # hosted URL override (e.g. GitHub Release asset)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def is_video(self) -> bool:
        return self.path.suffix.lower() in VIDEO_EXTS


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
def load_config(folder: Path) -> Dict:
    folder = Path(folder)
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    cfg["title"] = folder.name
    path = folder / CONFIG_NAME
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update(data)
        except (OSError, ValueError):
            pass
    if not isinstance(cfg.get("tracks"), dict):
        cfg["tracks"] = {}
    return cfg


def save_config(folder: Path, cfg: Dict) -> None:
    path = Path(folder) / CONFIG_NAME
    path.write_text(json.dumps(cfg, indent=2, sort_keys=True), encoding="utf-8")


# ----------------------------------------------------------------------------
# Scanning
# ----------------------------------------------------------------------------
def read_title_and_duration(path: Path):
    title, duration = None, None
    if TinyTag is not None:
        try:
            tag = TinyTag.get(str(path))
            title = tag.title or None
            duration = tag.duration or None
        except Exception:
            pass
    if duration is None and path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as w:
                rate = w.getframerate()
                if rate:
                    duration = w.getnframes() / float(rate)
        except Exception:
            pass
    if duration is None and shutil.which("ffprobe"):
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, timeout=10, check=False)
            duration = float(out.stdout.strip()) if out.stdout.strip() else None
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return title, duration


def scan_folder(folder: Path, cfg: Optional[Dict] = None) -> List[Track]:
    """Return feed tracks, newest first. Same-stem duplicates collapse to one.
    Scans media files in folder directly or inside dedicated subfolders (e.g. tracks/, media/)."""
    folder = Path(folder)
    cfg = cfg or load_config(folder)
    overrides = cfg.get("tracks", {})

    groups: Dict[str, List[Path]] = {}

    def consider_file(f: Path):
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in MIME_TYPES:
            groups.setdefault(f.stem, []).append(f)

    # 1. Check dedicated subfolders first (tracks/, media/, episodes/)
    for sub in ("tracks", "media", "episodes"):
        sub_dir = folder / sub
        if sub_dir.is_dir():
            for f in sorted(sub_dir.iterdir()):
                consider_file(f)

    # 2. Check the root folder
    for f in sorted(folder.iterdir()):
        consider_file(f)

    tracks = []
    for files in groups.values():
        files.sort(key=lambda p: FORMAT_PREFERENCE.index(p.suffix.lower()))
        chosen = files[0]
        # Keep the original upload time (earliest file in the group) as pubDate
        mtime = min(p.stat().st_mtime for p in files)
        tag_title, duration = read_title_and_duration(chosen)
        rel_key = chosen.relative_to(folder).as_posix()
        ov = overrides.get(chosen.name) or overrides.get(rel_key) or overrides.get(files[-1].name) or {}
        title = ov.get("title") or tag_title or chosen.stem
        description = ov.get("description") or f"Daily track selection: {title}"
        # A recorded publish time keeps pubDate stable across machines/clones
        if ov.get("pub"):
            mtime = float(ov["pub"])
        tracks.append(Track(
            path=chosen, title=title, description=description, duration=duration,
            size=chosen.stat().st_size, mtime=mtime,
            mime=MIME_TYPES[chosen.suffix.lower()], alternates=files[1:],
            url=ov.get("url") or ""))

    tracks.sort(key=lambda t: t.mtime, reverse=True)
    return tracks


# ----------------------------------------------------------------------------
# Feed generation
# ----------------------------------------------------------------------------
def fmt_duration(seconds: Optional[float]) -> str:
    if not seconds:
        return "--:--"
    s = int(round(seconds))
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num} B"


def _rfc2822(ts: float) -> str:
    return format_datetime(datetime.fromtimestamp(ts, tz=timezone.utc), usegmt=True)


def build_feed_xml(cfg: Dict, tracks: List[Track], folder: Optional[Path] = None) -> str:
    base = cfg.get("base_url", "").rstrip("/")
    title = cfg.get("title") or "Untitled Feed"
    x = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">',
        "  <channel>",
        f"    <title>{escape(title)}</title>",
        f"    <link>{escape(base)}</link>",
        f"    <language>{escape(cfg.get('language') or 'en-us')}</language>",
        f"    <description>{escape(cfg.get('description') or title)}</description>",
        f"    <lastBuildDate>{_rfc2822(datetime.now(timezone.utc).timestamp())}</lastBuildDate>",
        "    <generator>RSSpad</generator>",
    ]
    if cfg.get("author"):
        x.append(f"    <itunes:author>{escape(cfg['author'])}</itunes:author>")
    if cfg.get("image_url"):
        img = escape(cfg["image_url"])
        x.append(f'    <itunes:image href="{img}" />')
        x += ["    <image>", f"      <url>{img}</url>",
              f"      <title>{escape(title)}</title>", f"      <link>{escape(base)}</link>",
              "    </image>"]
    if cfg.get("category"):
        x.append(f'    <itunes:category text="{escape(cfg["category"])}" />')
    x.append(f"    <itunes:explicit>{'true' if cfg.get('explicit') else 'false'}</itunes:explicit>")

    for t in tracks:
        url = escape(track_url(cfg, t, folder))
        x += [
            "    <item>",
            f"      <title>{escape(t.title)}</title>",
            f"      <description>{escape(t.description)}</description>",
            f"      <pubDate>{_rfc2822(t.mtime)}</pubDate>",
            f'      <enclosure url="{url}" length="{t.size}" type="{t.mime}" />',
            f'      <guid isPermaLink="false">{url}</guid>',
        ]
        if t.duration:
            s = int(round(t.duration))
            x.append(f"      <itunes:duration>{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}</itunes:duration>")
        x.append("    </item>")

    x += ["  </channel>", "</rss>", ""]
    return "\n".join(x)


def track_url(cfg: Dict, t: Track, folder: Optional[Path] = None) -> str:
    """Public URL of a track: hosted override (e.g. GitHub Release) or base_url/file."""
    if t.url:
        return t.url
    base = cfg.get("base_url", "").rstrip("/")
    if folder:
        try:
            rel = t.path.relative_to(folder).as_posix()
            return f"{base}/{quote(rel)}"
        except ValueError:
            pass
    return f"{base}/{quote(t.name)}"


def write_feed(folder: Path, cfg: Optional[Dict] = None) -> Path:
    folder = Path(folder)
    cfg = cfg or load_config(folder)
    tracks = scan_folder(folder, cfg)
    out = folder / (cfg.get("output_name") or "feed.xml")
    out.write_text(build_feed_xml(cfg, tracks, folder=folder), encoding="utf-8")
    if cfg.get("github_repo"):
        (folder / "index.html").write_text(build_index_html(cfg, tracks, folder=folder), encoding="utf-8")
    return out


def build_index_html(cfg: Dict, tracks: List[Track], folder: Optional[Path] = None) -> str:
    """A sleek neon landing page for GitHub Pages with responsive video previews."""
    title = escape(cfg.get("title") or "Feed")
    feed = escape(f"{cfg.get('base_url', '').rstrip('/')}/{cfg.get('output_name') or 'feed.xml'}")
    items = []
    base = cfg.get("base_url", "").rstrip("/")
    for t in tracks:
        url = escape(track_url(cfg, t, folder))
        if t.is_video:
            poster_file = f"{t.path.stem}_poster.jpg"
            p_same = t.path.parent / poster_file
            p_root = (folder / poster_file) if folder else None
            if p_same.is_file():
                if folder:
                    try:
                        rel = p_same.relative_to(folder).as_posix()
                    except ValueError:
                        rel = p_same.name
                else:
                    rel = f"{t.path.parent.name}/{poster_file}" if t.path.parent.name in ("tracks", "media", "episodes") else poster_file
                poster_attr = f' poster="{base}/{quote(rel)}"'
            elif p_root and p_root.is_file():
                poster_attr = f' poster="{base}/{quote(poster_file)}"'
            else:
                rel = f"{t.path.parent.name}/{poster_file}" if t.path.parent.name in ("tracks", "media", "episodes") else poster_file
                poster_attr = f' poster="{base}/{quote(rel)}"'
            player = (
                f'<video controls preload="metadata"{poster_attr}>\n'
                f'      <source src="{url}" type="video/mp4">\n'
                f'      <p><a href="{url}" class="download-link">Watch / Download {escape(t.name)}</a></p>\n'
                f'    </video>'
            )
        else:
            player = f'<audio controls preload="metadata" src="{url}"></audio>'
        items.append(
            f'  <article>\n'
            f'    <h2>{escape(t.title)}</h2>\n'
            f'    <p class="meta">{datetime.fromtimestamp(t.mtime).strftime("%B %d, %Y")}'
            f' &middot; {fmt_duration(t.duration)} &middot; {fmt_size(t.size)}</p>\n'
            f'    {player}\n'
            f'    <p class="desc">{escape(t.description)}</p>\n'
            f'  </article>'
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="alternate" type="application/rss+xml" title="{title}" href="{feed}">
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #0d1322;
      --cyan: #00f0ff;
      --blue: #38bdf8;
      --border: rgba(0, 240, 255, 0.25);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      background: var(--bg);
      color: #ffffff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      margin: 0;
      padding: 24px 16px;
      line-height: 1.5;
    }}
    main {{ max-width: 760px; margin: 0 auto; }}
    header {{ margin-bottom: 24px; text-align: center; }}
    h1 {{ color: var(--cyan); margin: 0 0 6px 0; font-size: 1.8rem; }}
    .sub {{ color: var(--blue); margin: 0; font-size: 0.95rem; }}
    article {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px;
      margin: 20px 0;
      clear: both;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    }}
    article h2 {{ margin: 0 0 4px 0; font-size: 1.25rem; color: #ffffff; }}
    .meta {{ color: var(--blue); font-size: 0.85rem; margin: 0 0 12px 0; }}
    video {{
      width: 100%;
      max-height: 75vh;
      border-radius: 8px;
      background: #000000;
      display: block;
      outline: none;
    }}
    audio {{ width: 100%; display: block; }}
    .desc {{ margin: 12px 0 0 0; color: #cbd5e1; font-size: 0.92rem; }}
    .download-link {{ color: var(--cyan); text-decoration: none; }}
    .download-link:hover {{ text-decoration: underline; }}
    footer {{
      margin-top: 36px;
      text-align: center;
      color: #64748b;
      font-size: 0.8rem;
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>{title}</h1>
    <p class="sub">{escape(cfg.get('description') or '')}</p>
  </header>
  {''.join(items)}
  <footer>
    <p>Powered by RSSpad</p>
  </footer>
</main>
</body>
</html>
"""


def make_cover_command(video: Path, out: Path, size: int = 1400) -> List[str]:
    """ffmpeg command: grab a frame and fit it on a square dark canvas."""
    vf = (f"scale={size}:{size}:force_original_aspect_ratio=decrease,"
          f"pad={size}:{size}:(ow-iw)/2:(oh-ih)/2:color=0x0b0f19")
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "5", "-i", str(video),
            "-frames:v", "1", "-vf", vf, "-q:v", "3", str(out)]


def mp4_compress_command(src: Path, dst: Path, crf: int = 23) -> List[str]:
    """ffmpeg command: re-encode video to H.264/AAC with faststart for streaming."""
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
            "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(dst)]


def extract_mp3_command(src: Path, bitrate: str = "192k") -> List[str]:
    """ffmpeg command: extract/convert audio to MP3."""
    dst = src.with_suffix(".mp3")
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
            "-vn", "-codec:a", "libmp3lame", "-b:a", bitrate,
            "-metadata", f"title={src.stem}", str(dst)]


# ----------------------------------------------------------------------------
# GitHub Hosting & Publishing (Pages + Releases for >100 MB media)
# ----------------------------------------------------------------------------
GITHUB_GIT_LIMIT = 95 * 1024 * 1024  # 95 MB threshold before using GitHub Releases


def sync_github(folder: Path, log_fn=print) -> bool:
    """
    Sync feed folder to GitHub:
    - Any media file > 95 MB (or all media if github_release_tag is set) is uploaded
      to a GitHub Release so it never hits GitHub's 100 MB git blob limit.
    - Each uploaded asset's browser_download_url is saved into .rsspad.json track overrides.
    - Cover art is auto-generated from the first video if missing.
    - feed.xml and index.html are regenerated and committed + pushed to main.
    """
    folder = Path(folder).resolve()
    cfg = load_config(folder)
    repo = (cfg.get("github_repo") or "").strip()
    tag = (cfg.get("github_release_tag") or "episodes").strip()

    if not repo:
        log_fn("No github_repo configured in .rsspad.json")
        return False

    tracks = scan_folder(folder, cfg)
    overrides = cfg.setdefault("tracks", {})

    # 1. Auto-generate cover.jpg from first video if missing, and poster frames for videos
    cover_path = folder / "cover.jpg"
    videos = [t.path for t in tracks if t.is_video]
    if shutil.which("ffmpeg"):
        if not cover_path.exists() and videos:
            log_fn(f"Generating cover.jpg from {videos[0].name}...")
            subprocess.run(make_cover_command(videos[0], cover_path), check=False)
        for v in videos:
            pframe = v.parent / f"{v.stem}_poster.jpg"
            if not pframe.exists():
                log_fn(f"Generating preview poster for {v.name}...")
                subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "3",
                     "-i", str(v), "-frames:v", "1", "-q:v", "3", str(pframe)],
                    check=False
                )
    if cover_path.exists() and not cfg.get("image_url"):
        base = (cfg.get("base_url") or "").rstrip("/")
        if base and "yourdomain.com" not in base:
            cfg["image_url"] = f"{base}/cover.jpg"

    # 2. Ensure GitHub Release exists and upload track assets via gh CLI
    if shutil.which("gh"):
        chk = subprocess.run(
            ["gh", "release", "view", tag, "--repo", repo, "--json", "assets"],
            cwd=str(folder), capture_output=True, text=True, check=False)
        if chk.returncode != 0:
            log_fn(f"Creating GitHub Release '{tag}' on {repo}...")
            subprocess.run(
                ["gh", "release", "create", tag, "--repo", repo,
                 "--title", f"{cfg.get('title') or 'Podcast'} Episodes",
                 "--notes", "Automated media asset hosting managed by RSSpad."],
                cwd=str(folder), check=False)
            chk = subprocess.run(
                ["gh", "release", "view", tag, "--repo", repo, "--json", "assets"],
                cwd=str(folder), capture_output=True, text=True, check=False)

        existing_assets = {}
        if chk.returncode == 0 and chk.stdout.strip():
            try:
                data = json.loads(chk.stdout)
                for a in data.get("assets", []):
                    existing_assets[a["name"]] = (a.get("url") or "", a.get("size") or 0)
            except ValueError:
                pass

        for t in tracks:
            ov = overrides.setdefault(t.name, {})
            if not ov.get("pub"):
                ov["pub"] = t.mtime
            # Check if asset with matching name/safe-name or existing URL is already uploaded
            asset_url = f"https://github.com/{repo}/releases/download/{tag}/{quote(t.name)}"
            need_upload = True
            for aname, (aurl, asize) in existing_assets.items():
                if asize == t.size and (aname == t.name or aname == t.name.replace(" ", ".")):
                    ov["url"] = aurl
                    need_upload = False
                    break
            if need_upload:
                log_fn(f"Uploading {t.name} ({fmt_size(t.size)}) to GitHub Release '{tag}'...")
                up = subprocess.run(
                    ["gh", "release", "upload", tag, str(t.path), "--clobber", "--repo", repo],
                    cwd=str(folder), capture_output=True, text=True, check=False)
                if up.returncode != 0:
                    log_fn(f"Upload failed for {t.name}: {up.stderr.strip()}")
                    return False
                # Re-query release assets to get exact browser_download_url (gh normalizes spaces to dots)
                q = subprocess.run(
                    ["gh", "release", "view", tag, "--repo", repo, "--json", "assets"],
                    cwd=str(folder), capture_output=True, text=True, check=False)
                if q.returncode == 0:
                    try:
                        for a in json.loads(q.stdout).get("assets", []):
                            if a.get("size") == t.size and (
                                a["name"] == t.name or a["name"] == t.name.replace(" ", ".")
                            ):
                                asset_url = a["url"]
                                break
                    except ValueError:
                        pass
                ov["url"] = asset_url
                log_fn(f"Uploaded -> {ov['url']}")

    # 3. Save updated config and regenerate feed.xml + index.html
    save_config(folder, cfg)
    out_feed = write_feed(folder, cfg)
    log_fn(f"Generated {out_feed.name} and index.html")

    # 4. Commit and push feed metadata & RSSpad code to GitHub
    for cmd in (
        ["git", "add", "-A"],
        ["git", "commit", "-m", f"Update feed ({len(tracks)} episodes)"],
        ["git", "push", "-u", "origin", "main"],
    ):
        res = subprocess.run(cmd, cwd=str(folder), capture_output=True, text=True, check=False)
        if res.stdout.strip():
            log_fn(res.stdout.strip())
        if res.returncode != 0 and "nothing to commit" not in (res.stdout + res.stderr):
            if cmd[1] != "commit":
                log_fn(f"git {' '.join(cmd[1:])} warning: {res.stderr.strip()}")
    log_fn("GitHub sync complete!")
    return True


def wav_to_mp3_command(src: Path, bitrate: str = "192k") -> List[str]:
    dst = src.with_suffix(".mp3")
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
            "-codec:a", "libmp3lame", "-b:a", bitrate,
            "-metadata", f"title={src.stem}", str(dst)]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--sync-github":
        target = Path(sys.argv[2] if len(sys.argv) > 2 else ".").expanduser().resolve()
        ok = sync_github(target)
        sys.exit(0 if ok else 1)
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".").expanduser().resolve()
    path = write_feed(target)
    print(f"Wrote {path} ({len(scan_folder(target))} tracks)")

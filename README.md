# RSSpad

<p align="center">
  <img src="rsspad.svg" alt="RSSpad Logo" width="160" height="160">
</p>

A fast, modern **Podcast & RSS 2.0 Feed Studio** with **Live Folder Watching**, **GitHub Releases + GitHub Pages Publishing**, **Integrated GStreamer Media Playback**, **FFmpeg Audio/Cover Tools**, **Local Wi-Fi LAN Preview Server**, and a translucent darker-blue RSS emblem resting on an unassuming yoga pad. Built natively for **Linux Mint Cinnamon** using Python 3, GTK 3, GtkSourceView 4, and GStreamer.

---

## Key Features

### Automatic Video & Audio Feed Generation
- **Multi-Format Episode Scanning**: Automatically detects `.mp4`, `.m4v`, `.mov`, `.mp3`, `.m4a`, `.aac`, `.ogg`, `.opus`, `.flac`, and `.wav` files in any feed folder, reads durations and sizes via `ffprobe`/`tinytag`/`wave`, and writes a compliant iTunes & RSS 2.0 `feed.xml`.
- **Live Folder Monitoring**: Watches your feed directory using `Gio.FileMonitor` and automatically updates `feed.xml` whenever you drop in or rename media files.
- **Per-Episode Metadata Editor**: Customize individual episode titles and descriptions while preserving original publish timestamps in `.rsspad.json`.

### One-Click GitHub Releases + Pages Hosting (`F6`)
- **Bypass the 100 MB Git Limit**: Large `.mp4` video episodes or lossless audio files are automatically uploaded to a GitHub Release (`episodes` tag, up to 2 GB per file) via the GitHub CLI (`gh`), and their direct streaming URLs are linked as `<enclosure>` tags in `feed.xml`.
- **Web Player Landing Page (`index.html`)**: Automatically builds a dark-neon HTML5 video/audio landing page alongside `feed.xml` for GitHub Pages.
- **Custom Publish Commands**: Alternatively run any custom `rsync`, `rclone`, or `git push` command on publish.

### Integrated Media Tools & Preview
- **Built-in GStreamer Player (`Space`)**: Play or pause audio and video tracks directly inside RSSpad with live position/duration feedback in the status bar.
- **FFmpeg Cover Art & MP3 Extraction**: Generate square 1400x1400 podcast cover art (`cover.jpg`) from any video track or batch-extract `.mp3` audio from `.mp4`/`.wav` files.
- **Local LAN Preview Server**: One-click HTTP server (`http://<lan-ip>:8765/feed.xml`) to test your feed in any podcast app over local Wi-Fi before publishing.
- **Live `feed.xml` Inspector**: View syntax-highlighted XML output in real time using the `pythonpad-neon` GtkSourceView scheme.
- **User Manual**: Includes a concise 2-page dark-neon [RSSpad User Manual (PDF)](RSSpad%20User%20Manual.pdf).

---

## Installation

```bash
./install.sh
```

The installer automatically:
- Installs the vector icon (`rsspad.svg`) and multi-size panel icon set (`16x16` through `512x512`) into `~/.local/share/icons/hicolor/`.
- Installs the desktop launcher (`~/.local/share/applications/rsspad.desktop`) with `StartupWMClass=rsspad`.
- Creates the CLI command symlink at `~/.local/bin/rsspad`.
- Pins **RSSpad** to your Cinnamon Menu favorites and taskbar panel.

---

## Usage

```bash
# Launch RSSpad GUI (opens your last feed folder or ~/Music by default)
rsspad

# Open a specific media folder in RSSpad
rsspad /path/to/your/media-folder

# Headless CLI: generate feed.xml for a folder
python3 feed_core.py /path/to/your/media-folder

# Headless CLI: upload new media to GitHub Releases & publish feed.xml to GitHub Pages
python3 feed_core.py --sync-github /path/to/your/media-folder
```

---

## Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `F5` / `Ctrl + S` | Generate `feed.xml` |
| `F6` | Generate & Publish (GitHub Sync or custom publish command) |
| `Ctrl + O` | Open feed folder |
| `Ctrl + I` | Add media tracks to feed |
| `Ctrl + R` | Rescan folder |
| `Ctrl + B` / `F9` | Toggle Feed Settings sidebar |
| `Space` | Play / Pause selected track |
| `Ctrl + Shift + C` | Copy public Feed URL to clipboard |
| `Delete` | Rename or move selected track to Trash |
| `Ctrl + 1 / 2 / 3` | Switch between Tracks, `feed.xml`, and Activity Log |
| `Ctrl + Q` | Quit RSSpad |

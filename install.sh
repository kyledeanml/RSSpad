#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
BIN_DIR="$HOME/.local/bin"

echo "=========================================================="
echo " Installing RSSpad for Linux Mint Cinnamon"
echo " (Podcast & RSS Feed Studio - PythonPad family)"
echo "=========================================================="

chmod +x "$DIR/run.sh" "$DIR/rsspad.py" "$DIR/feed_core.py"
mkdir -p "$APP_DIR" "$ICONS_DIR" "$BIN_DIR" "$HOME/.local/share/pixmaps"

# 1. Icons
cp -f "$DIR/rsspad.svg" "$ICONS_DIR/rsspad.svg"
cp -f "$DIR/rsspad.svg" "$HOME/.local/share/pixmaps/rsspad.svg"
python3 -B -c "
import os, gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf
src = '$DIR/rsspad.svg'
base = os.path.expanduser('~/.local/share/icons/hicolor')
for sz in (16, 24, 32, 48, 64, 128, 256, 512):
    out_dir = os.path.join(base, f'{sz}x{sz}', 'apps')
    os.makedirs(out_dir, exist_ok=True)
    GdkPixbuf.Pixbuf.new_from_file_at_scale(src, sz, sz, True).savev(
        os.path.join(out_dir, 'rsspad.png'), 'png', [], [])
" 2>/dev/null || true
echo "[+] Installed RSSpad icon set"

# 2. CLI launcher
ln -sf "$DIR/run.sh" "$BIN_DIR/rsspad"
echo "[+] Created CLI executable link: $BIN_DIR/rsspad"

# 3. Desktop entry
cat <<EOF > "$APP_DIR/rsspad.desktop"
[Desktop Entry]
Name=RSSpad
Comment=Podcast & RSS feed studio: turn a folder of audio tracks into a podcast feed
GenericName=Podcast Feed Generator
Exec=$DIR/run.sh %F
Icon=rsspad
Terminal=false
Type=Application
Categories=GTK;GNOME;AudioVideo;Audio;Network;Utility;
MimeType=inode/directory;
StartupNotify=true
StartupWMClass=rsspad
Keywords=rss;podcast;feed;audio;music;mp3;wav;publish;
EOF
chmod +x "$APP_DIR/rsspad.desktop"
echo "[+] Installed desktop entry: $APP_DIR/rsspad.desktop"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo ""
echo "Done! Launch RSSpad from the Cinnamon menu (Sound & Video / Accessories)"
echo "or run:  rsspad  [folder]"

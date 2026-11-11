#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
BIN_DIR="$HOME/.local/bin"
STYLES_DIR="$HOME/.local/share/gtksourceview-4/styles"

echo "=========================================================="
echo " Installing RSSpad for Linux Mint Cinnamon"
echo " (Podcast & RSS Feed Studio - PythonPad family)"
echo "=========================================================="

chmod +x "$DIR/run.sh" "$DIR/rsspad.py" "$DIR/feed_core.py"
mkdir -p "$APP_DIR" "$ICONS_DIR" "$BIN_DIR" "$STYLES_DIR" "$HOME/.icons" "$HOME/.local/share/pixmaps"

# 1. Install high-DPI vector icon & multi-size PNG icons for Cinnamon panel / menus
cp -f "$DIR/rsspad.svg" "$ICONS_DIR/rsspad.svg"
cp -f "$DIR/rsspad.svg" "$HOME/.icons/rsspad.svg"
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
echo "[+] Installed RSSpad SVG & panel icon set: $ICONS_DIR/rsspad.svg"

if [ -d "$DIR/styles" ]; then
    cp -r "$DIR/styles/"* "$STYLES_DIR/"
    echo "[+] Installed GtkSource style schemes: $STYLES_DIR"
fi

# 2. CLI launcher
ln -sf "$DIR/run.sh" "$BIN_DIR/rsspad"
echo "[+] Created CLI executable link: $BIN_DIR/rsspad"

# 3. Desktop entry (quoted Exec path so spaces in folder paths work cleanly)
cat <<EOF > "$APP_DIR/rsspad.desktop"
[Desktop Entry]
Name=RSSpad
Comment=Podcast & RSS feed studio: turn a folder of video & audio tracks into a podcast feed
GenericName=Podcast & RSS Feed Studio
Exec="$DIR/run.sh" %F
Icon=$ICONS_DIR/rsspad.svg
Terminal=false
Type=Application
Categories=GTK;GNOME;AudioVideo;Audio;Video;Network;Utility;
MimeType=application/rss+xml;inode/directory;
StartupNotify=true
StartupWMClass=rsspad
Keywords=rss;podcast;feed;audio;video;mp4;music;mp3;wav;publish;github;
Actions=NewWindow;

[Desktop Action NewWindow]
Name=Open a New Window
Exec="$DIR/run.sh"
EOF
chmod +x "$APP_DIR/rsspad.desktop"
echo "[+] Installed desktop entry: $APP_DIR/rsspad.desktop"

# 4. Refresh desktop database & icon caches
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

# 5. Add RSSpad to Cinnamon Menu favorites
if command -v gsettings >/dev/null 2>&1; then
    python3 -c "
import gi
from gi.repository import Gio
try:
    settings = Gio.Settings.new('org.cinnamon')
    favs = list(settings.get_strv('favorite-apps'))
    if 'rsspad.desktop' not in favs:
        favs.append('rsspad.desktop')
    settings.set_strv('favorite-apps', favs)
    print('[+] Added RSSpad to Cinnamon favorite apps')
except Exception:
    pass
" || true
fi

echo ""
echo "=========================================================="
echo " Installation Complete!"
echo "=========================================================="
echo "Launch RSSpad from the Cinnamon menu (Favorites / Sound & Video)"
echo "or run from terminal:  rsspad"
echo "=========================================================="

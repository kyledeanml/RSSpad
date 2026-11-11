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

mkdir -p "$APP_DIR"
mkdir -p "$ICONS_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$STYLES_DIR"

# 1. Install high-DPI vector icon & multi-size PNG icons for Cinnamon panel / menus
cp -f "$DIR/rsspad.svg" "$ICONS_DIR/rsspad.svg"
mkdir -p "$HOME/.icons" "$HOME/.local/share/pixmaps"
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
    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(src, sz, sz, True)
    pb.savev(os.path.join(out_dir, 'rsspad.png'), 'png', [], [])
" 2>/dev/null || true

echo "[+] Installed RSSpad SVG & panel icon set: $ICONS_DIR/rsspad.svg"
if [ -d "$DIR/styles" ]; then
    cp -r "$DIR/styles/"* "$STYLES_DIR/"
    echo "[+] Installed GtkSource style schemes: $STYLES_DIR"
fi

# 2. Install executable launcher in ~/.local/bin
ln -sf "$DIR/run.sh" "$BIN_DIR/rsspad"
echo "[+] Created CLI executable link: $BIN_DIR/rsspad"

# 3. Write desktop launcher for Cinnamon Menu and Panel matching PythonPad format
cat <<EOF > "$APP_DIR/rsspad.desktop"
[Desktop Entry]
Name=RSSpad
Comment=Podcast & RSS feed studio: turn a folder of video & audio tracks into a podcast feed
GenericName=Podcast & RSS Feed Studio
Exec=$DIR/run.sh %F
Icon=$ICONS_DIR/rsspad.svg
Terminal=false
Type=Application
Categories=GTK;GNOME;AudioVideo;Audio;Video;Utility;
MimeType=application/rss+xml;inode/directory;
StartupNotify=true
StartupWMClass=rsspad
Keywords=rss;podcast;feed;audio;video;mp4;music;mp3;wav;publish;github;
Actions=NewWindow;

[Desktop Action NewWindow]
Name=Open a New Window
Exec=$DIR/run.sh
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

# 5. Enable Cinnamon Menu favorites & pin to taskbar
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

python3 -B -c "
import os, glob, json
for cfg_path in glob.glob(os.path.expanduser('~/.config/cinnamon/spices/grouped-window-list@cinnamon.org/*.json')):
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        pinned = data.get('pinned-apps', {}).get('value')
        if isinstance(pinned, list) and 'rsspad.desktop' not in pinned:
            pinned.append('rsspad.desktop')
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            print('[+] Pinned RSSpad to Cinnamon grouped-window-list panel')
    except Exception:
        pass
" || true

echo ""
echo "=========================================================="
echo " Installation Complete!"
echo "=========================================================="
echo "To place RSSpad on your Linux Mint Cinnamon panel:"
echo "  1. Click your Cinnamon Menu button (bottom-left)."
echo "  2. Search for 'RSSpad' (under Sound & Video or Favorites)."
echo "  3. Right-click 'RSSpad' and select 'Add to panel'."
echo "     (Or drag the RSSpad icon from the menu and drop"
echo "      it directly onto your panel)."
echo ""
echo "You can also launch it anytime from terminal by typing:"
echo "  rsspad"
echo "=========================================================="

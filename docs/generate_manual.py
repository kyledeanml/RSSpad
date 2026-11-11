#!/usr/bin/env python3
"""Generate a compact, dense, beautifully structured RSSpad Quick Reference & Manual PDF."""

import os
import sys
import cairo
import gi

gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Pango, PangoCairo, GdkPixbuf, Gdk

PAGE_WIDTH = 612   # Letter 8.5 x 11 in points
PAGE_HEIGHT = 792
MARGIN_X = 36      # Compact 0.5 in margins
MARGIN_TOP = 32
MARGIN_BOTTOM = 32
CONTENT_WIDTH = PAGE_WIDTH - (MARGIN_X * 2)  # 540 pt wide

class CompactPDFBuilder:
    def __init__(self, filename):
        self.filename = filename
        self.surface = cairo.PDFSurface(filename, PAGE_WIDTH, PAGE_HEIGHT)
        self.cr = cairo.Context(self.surface)
        self.page_num = 1
        self.y = MARGIN_TOP
        self._start_page()

    def _start_page(self):
        # Deep dark canvas (#0b0f19)
        self.cr.save()
        self.cr.set_source_rgb(0.043, 0.059, 0.098)
        self.cr.paint()

        # Ultra-slim top accent line (2pt)
        pat = cairo.LinearGradient(0, 0, PAGE_WIDTH, 0)
        pat.add_color_stop_rgb(0.0, 0.0, 0.94, 1.0)   # #00f0ff
        pat.add_color_stop_rgb(0.5, 0.22, 0.74, 0.97) # #38bdf8
        pat.add_color_stop_rgb(1.0, 0.01, 0.35, 0.55) # #035a8c
        self.cr.set_source(pat)
        self.cr.rectangle(0, 0, PAGE_WIDTH, 2.5)
        self.cr.fill()
        self.cr.restore()
        self.y = MARGIN_TOP

    def _draw_footer(self):
        self.cr.save()
        self.cr.set_source_rgba(0.0, 0.94, 1.0, 0.2)
        self.cr.set_line_width(0.5)
        self.cr.move_to(MARGIN_X, PAGE_HEIGHT - 22)
        self.cr.line_to(PAGE_WIDTH - MARGIN_X, PAGE_HEIGHT - 22)
        self.cr.stroke()

        layout = PangoCairo.create_layout(self.cr)
        layout.set_markup(
            '<span foreground="#64748b" font="Sans 7.5">RSSpad Manual  &#x2022;  PythonPad Creative Suite  &#x2022;  Linux Mint Cinnamon</span>'
        )
        self.cr.move_to(MARGIN_X, PAGE_HEIGHT - 17)
        PangoCairo.show_layout(self.cr, layout)

        layout_num = PangoCairo.create_layout(self.cr)
        layout_num.set_markup(
            f'<span foreground="#00f0ff" font="Sans Bold 7.5">Page {self.page_num} of 2</span>'
        )
        _, ext = layout_num.get_pixel_extents()
        self.cr.move_to(PAGE_WIDTH - MARGIN_X - ext.width, PAGE_HEIGHT - 17)
        PangoCairo.show_layout(self.cr, layout_num)
        self.cr.restore()

    def new_page(self):
        self._draw_footer()
        self.surface.show_page()
        self.page_num += 1
        self._start_page()

    def check_space(self, height_needed):
        if self.y + height_needed > (PAGE_HEIGHT - MARGIN_BOTTOM - 12):
            self.new_page()

    def add_pango_text(self, markup, x=MARGIN_X, width=CONTENT_WIDTH):
        layout = PangoCairo.create_layout(self.cr)
        layout.set_width(int(width * Pango.SCALE))
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        layout.set_markup(markup)
        _, ext = layout.get_pixel_extents()
        self.check_space(ext.height)
        self.cr.move_to(x, self.y)
        PangoCairo.show_layout(self.cr, layout)
        self.y += ext.height
        return ext.height

    def add_section_header(self, title, icon="&#x25C6;"):
        self.check_space(26)
        layout = PangoCairo.create_layout(self.cr)
        layout.set_markup(f'<span foreground="#00f0ff" font="Sans Bold 11">{icon} {title}</span>')
        self.cr.move_to(MARGIN_X, self.y)
        PangoCairo.show_layout(self.cr, layout)
        self.y += 15

        self.cr.save()
        self.cr.set_source_rgba(0.0, 0.94, 1.0, 0.35)
        self.cr.set_line_width(0.75)
        self.cr.move_to(MARGIN_X, self.y)
        self.cr.line_to(MARGIN_X + CONTENT_WIDTH, self.y)
        self.cr.stroke()
        self.cr.restore()
        self.y += 6

    def add_dense_bullet(self, title, desc):
        markup = (
            f'<span foreground="#38bdf8" font="Sans Bold 8.5">• {title}: </span>'
            f'<span foreground="#cbd5e1" font="Sans 8.5">{desc}</span>'
        )
        self.add_pango_text(markup)
        self.y += 2

    def add_compact_box(self, title, text, bg_rgb=(0.06, 0.09, 0.15), border_rgb=(0.0, 0.94, 1.0)):
        layout = PangoCairo.create_layout(self.cr)
        layout.set_width(int((CONTENT_WIDTH - 16) * Pango.SCALE))
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        markup = (
            f'<span foreground="#00f0ff" font="Sans Bold 8">[{title}] </span>'
            f'<span foreground="#e0f2fe" font="Sans 8">{text}</span>'
        )
        layout.set_markup(markup)
        _, ext = layout.get_pixel_extents()
        total_h = ext.height + 8
        self.check_space(total_h + 4)

        self.cr.save()
        self.cr.set_source_rgb(*bg_rgb)
        self.cr.rectangle(MARGIN_X, self.y, CONTENT_WIDTH, total_h)
        self.cr.fill()

        # Thin left highlight
        self.cr.set_source_rgb(*border_rgb)
        self.cr.rectangle(MARGIN_X, self.y, 2.5, total_h)
        self.cr.fill()

        # Thin border
        self.cr.set_source_rgba(border_rgb[0], border_rgb[1], border_rgb[2], 0.25)
        self.cr.set_line_width(0.5)
        self.cr.rectangle(MARGIN_X, self.y, CONTENT_WIDTH, total_h)
        self.cr.stroke()

        self.cr.move_to(MARGIN_X + 8, self.y + 4)
        PangoCairo.show_layout(self.cr, layout)
        self.cr.restore()
        self.y += total_h + 4

    def add_2col_grid(self, left_items, right_items, col_gap=14):
        col_w = (CONTENT_WIDTH - col_gap) / 2
        start_y = self.y

        # Left column
        max_y_left = start_y
        for title, desc in left_items:
            layout = PangoCairo.create_layout(self.cr)
            layout.set_width(int(col_w * Pango.SCALE))
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
            layout.set_markup(f'<span foreground="#38bdf8" font="Sans Bold 8">• {title}: </span><span foreground="#cbd5e1" font="Sans 8">{desc}</span>')
            _, ext = layout.get_pixel_extents()
            self.cr.move_to(MARGIN_X, self.y)
            PangoCairo.show_layout(self.cr, layout)
            self.y += ext.height + 2
        max_y_left = self.y

        # Right column
        self.y = start_y
        for title, desc in right_items:
            layout = PangoCairo.create_layout(self.cr)
            layout.set_width(int(col_w * Pango.SCALE))
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
            layout.set_markup(f'<span foreground="#38bdf8" font="Sans Bold 8">• {title}: </span><span foreground="#cbd5e1" font="Sans 8">{desc}</span>')
            _, ext = layout.get_pixel_extents()
            self.cr.move_to(MARGIN_X + col_w + col_gap, self.y)
            PangoCairo.show_layout(self.cr, layout)
            self.y += ext.height + 2
        max_y_right = self.y

        self.y = max(max_y_left, max_y_right) + 4

    def add_compact_table(self, headers, rows, col_widths=None):
        if not col_widths:
            col_widths = [110, CONTENT_WIDTH - 110]
        row_h = 16
        table_h = (len(rows) + 1) * row_h
        self.check_space(table_h + 4)

        self.cr.save()
        # Header background
        self.cr.set_source_rgb(0.06, 0.09, 0.15)
        self.cr.rectangle(MARGIN_X, self.y, CONTENT_WIDTH, row_h)
        self.cr.fill()

        # Header bottom line
        self.cr.set_source_rgba(0.0, 0.94, 1.0, 0.4)
        self.cr.set_line_width(0.75)
        self.cr.move_to(MARGIN_X, self.y + row_h)
        self.cr.line_to(MARGIN_X + CONTENT_WIDTH, self.y + row_h)
        self.cr.stroke()

        # Header text
        for i, h in enumerate(headers):
            layout = PangoCairo.create_layout(self.cr)
            layout.set_markup(f'<span foreground="#00f0ff" font="Sans Bold 8">{h}</span>')
            x_pos = MARGIN_X + 6 + (sum(col_widths[:i]) if i > 0 else 0)
            self.cr.move_to(x_pos, self.y + 2)
            PangoCairo.show_layout(self.cr, layout)
        self.y += row_h

        # Rows
        for r_idx, r in enumerate(rows):
            if r_idx % 2 == 1:
                self.cr.set_source_rgba(0.07, 0.11, 0.18, 0.4)
                self.cr.rectangle(MARGIN_X, self.y, CONTENT_WIDTH, row_h)
                self.cr.fill()

            self.cr.set_source_rgba(0.12, 0.18, 0.28, 0.4)
            self.cr.set_line_width(0.5)
            self.cr.move_to(MARGIN_X, self.y + row_h)
            self.cr.line_to(MARGIN_X + CONTENT_WIDTH, self.y + row_h)
            self.cr.stroke()

            # Col 0 (shortcut / key)
            layout_key = PangoCairo.create_layout(self.cr)
            layout_key.set_markup(f'<span foreground="#38bdf8" font="Monospace Bold 8">{r[0]}</span>')
            self.cr.move_to(MARGIN_X + 6, self.y + 2)
            PangoCairo.show_layout(self.cr, layout_key)

            # Col 1 (action / desc)
            layout_desc = PangoCairo.create_layout(self.cr)
            layout_desc.set_markup(f'<span foreground="#e2e8f0" font="Sans 8">{r[1]}</span>')
            self.cr.move_to(MARGIN_X + col_widths[0] + 6, self.y + 2)
            PangoCairo.show_layout(self.cr, layout_desc)
            self.y += row_h

        self.cr.restore()
        self.y += 6

    def finish(self):
        self._draw_footer()
        self.surface.show_page()
        self.surface.finish()


def build_compact_manual(output_pdf, icon_svg):
    builder = CompactPDFBuilder(output_pdf)

    # ------------------ COMPACT HERO HEADER ------------------
    header_h = 44
    builder.cr.save()
    pat = cairo.LinearGradient(MARGIN_X, builder.y, MARGIN_X + CONTENT_WIDTH, builder.y + header_h)
    pat.add_color_stop_rgba(0.0, 0.06, 0.11, 0.2, 0.85)
    pat.add_color_stop_rgba(1.0, 0.03, 0.06, 0.11, 0.95)
    builder.cr.set_source(pat)
    builder.cr.rectangle(MARGIN_X, builder.y, CONTENT_WIDTH, header_h)
    builder.cr.fill()

    builder.cr.set_source_rgba(0.0, 0.94, 1.0, 0.35)
    builder.cr.set_line_width(0.75)
    builder.cr.rectangle(MARGIN_X, builder.y, CONTENT_WIDTH, header_h)
    builder.cr.stroke()

    # App icon
    if icon_svg and os.path.exists(icon_svg):
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_svg, 34, 34, True)
            builder.cr.save()
            Gdk.cairo_set_source_pixbuf(builder.cr, pb, MARGIN_X + 8, builder.y + 5)
            builder.cr.paint()
            builder.cr.restore()
        except Exception:
            pass

    # Title & Subtitle in compact layout
    t_layout = PangoCairo.create_layout(builder.cr)
    t_layout.set_markup(
        '<span foreground="#ffffff" font="Sans Bold 14">RSS<span foreground="#00f0ff">pad</span></span> '
        '<span foreground="#38bdf8" font="Sans 9"> &#x2022;  Podcast &amp; RSS 2.0 Feed Studio  &#x2022;  User Manual &amp; Reference</span>'
    )
    builder.cr.move_to(MARGIN_X + 48, builder.y + 7)
    PangoCairo.show_layout(builder.cr, t_layout)

    sub_layout = PangoCairo.create_layout(builder.cr)
    sub_layout.set_markup(
        '<span foreground="#94a3b8" font="Sans 7.5">Linux Mint Cinnamon Desktop Integration  &#x2022;  Automated GitHub Releases + GitHub Pages Hosting</span>'
    )
    builder.cr.move_to(MARGIN_X + 48, builder.y + 24)
    PangoCairo.show_layout(builder.cr, sub_layout)

    builder.cr.restore()
    builder.y += header_h + 8

    # ------------------ SECTION: OVERVIEW & CORE ARCHITECTURE ------------------
    builder.add_section_header("Overview &amp; Core Architecture")
    builder.add_pango_text(
        '<span foreground="#e2e8f0" font="Sans 8.5"><b>RSSpad</b> is a lightweight GTK 3 desktop studio that converts any folder of video or audio tracks into an Apple Podcasts / iTunes-compliant RSS 2.0 feed and modern streaming web portal. Large media files bypass GitHub&#x2019;s 100 MB Git blob restriction by uploading directly to a GitHub Release, while the lightweight XML feed and responsive HTML player are pushed to GitHub Pages.</span>'
    )
    builder.y += 4

    builder.add_compact_box(
        "CORE HIGHLIGHTS",
        "Multi-format scanning (.mp4, .m4v, .mov, .mp3, .wav, .flac, .ogg, .m4a)  &#x2022;  Automatic video poster frame generation  &#x2022;  Native GStreamer media player  &#x2022;  Local Wi-Fi testing server  &#x2022;  Background file watcher  &#x2022;  PythonPad dark neon design.",
        border_rgb=(0.0, 0.94, 1.0)
    )

    # ------------------ SECTION: THE 3-STEP DAILY WORKFLOW ------------------
    builder.add_section_header("Daily Publishing Workflow")
    builder.add_2col_grid(
        [
            ("1. Drop Media", "Save or export your finished .mp4, .wav, or .mp3 track directly into your feed directory (or drag-and-drop into RSSpad)."),
            ("2. Auto-Detect", "RSSpad calculates runtime, size, auto-generates a clean video preview frame, and indexes the episode instantly.")
        ],
        [
            ("3. One-Click Publish (F6)", "Press F6 or click 'Generate &amp; Publish'. New episodes upload to GitHub Releases, and feed.xml + index.html update on Pages."),
            ("No Terminal Needed", "Runs completely hands-off. Podcast subscribers receive new tracks on their next refresh.")
        ]
    )

    # ------------------ SECTION: INTERFACE & TOOLBAR GUIDE ------------------
    builder.add_section_header("Interface Tour &amp; Toolbar Controls")
    left_tb = [
        ("Folder (Ctrl+O)", "Switch between feed directories or open an existing audio/video show."),
        ("Add Tracks (Ctrl+I)", "Import single or batch media files directly into the active feed folder."),
        ("Rescan (Ctrl+R)", "Refresh folder contents and recalculate durations/sizes."),
        ("Generate Feed (F5)", "Compile feed.xml and index.html locally without uploading.")
    ]
    right_tb = [
        ("Publish (F6)", "Upload new episodes to GitHub Releases and push updates to GitHub Pages."),
        ("LAN Server (Toggle)", "Starts Wi-Fi HTTP preview server (http://&lt;lan-ip&gt;:8765) for local phone testing."),
        ("Player (Space)", "Built-in GStreamer engine with status bar progress and play/pause."),
        ("Episode Editor", "Select any track in the list to customize show title &amp; description.")
    ]
    builder.add_2col_grid(left_tb, right_tb)

    # ------------------ SECTION: STUDIO WORKSPACE TABS ------------------
    builder.add_section_header("Studio Workspace Panels")
    builder.add_2col_grid(
        [
            ("Tracks Tab (Ctrl+1)", "View complete track table with status icons, episode titles, filenames, formats, durations, sizes, and timestamps."),
            ("feed.xml Tab (Ctrl+2)", "Live GtkSourceView syntax-highlighted preview of the exact XML document that podcast clients read.")
        ],
        [
            ("Activity Log (Ctrl+3)", "Real-time terminal log showing FFmpeg conversions, poster extraction, release uploads, and git push outputs."),
            ("Media Tools Menu", "Menu  &#x2192;  &#x2192;  Media &amp; Cover Tools allows extracting square cover art (cover.jpg) or batch converting tracks to 192k MP3.")
        ]
    )

    # ================== PAGE 2: REFERENCE, SHORTCUTS, CONFIG ==================
    builder.new_page()

    # ------------------ SECTION: KEYBOARD SHORTCUTS ------------------
    builder.add_section_header("Keyboard Shortcuts Quick Reference")
    shortcuts = [
        ("F5 / Ctrl + S", "Generate feed.xml &amp; index.html locally"),
        ("F6", "Generate &amp; Publish to GitHub Releases + Pages"),
        ("Ctrl + O", "Open a podcast / media channel folder"),
        ("Ctrl + I", "Import tracks into the active feed folder"),
        ("Ctrl + R", "Rescan folder and update media durations"),
        ("Ctrl + B / F9", "Toggle Feed Settings sidebar"),
        ("Space", "Play or pause selected audio/video track"),
        ("Delete", "Rename track or move file to Trash"),
        ("Ctrl + Shift + C", "Copy public feed.xml URL to clipboard"),
        ("Ctrl + 1 / 2 / 3", "Switch between Tracks, feed.xml, and Activity Log tabs"),
        ("Ctrl + Q", "Quit RSSpad"),
    ]
    builder.add_compact_table(["Shortcut", "Action Description"], shortcuts, col_widths=[105, CONTENT_WIDTH - 105])

    # ------------------ SECTION: CONFIGURATION SCHEMA ------------------
    builder.add_section_header("Configuration Schema (.rsspad.json)")
    builder.add_pango_text(
        '<span foreground="#e2e8f0" font="Sans 8">Channel configuration is saved in an unobtrusive <b>.rsspad.json</b> file inside your media directory:</span>'
    )
    builder.y += 4
    cfg_left = [
        ("base_url", "Public base URL for feed and web player (e.g. https://&lt;user&gt;.github.io/&lt;repo&gt;)."),
        ("github_repo", "Target repository ('owner/repo') used for GitHub Releases and Pages hosting."),
        ("github_release_tag", "Release tag name (default: 'episodes') where files over 95 MB are hosted.")
    ]
    cfg_right = [
        ("image_url", "Square podcast show artwork URL (1400x1400 to 3000x3000 px)."),
        ("title / description", "Show title and channel description visible in podcast directories."),
        ("publish_command", "Optional custom command (e.g. rsync or git) if not using GitHub.")
    ]
    builder.add_2col_grid(cfg_left, cfg_right)

    # ------------------ SECTION: CLI & HEADLESS AUTOMATION ------------------
    builder.add_section_header("Headless CLI &amp; Automation")
    builder.add_compact_box(
        "TERMINAL &amp; CRON USAGE",
        "<b># Compile feed locally:</b> python3 feed_core.py /path/to/media/folder\n"
        "<b># Upload &amp; publish to GitHub:</b> python3 feed_core.py --sync-github /path/to/media/folder\n"
        "<b># Launch GUI:</b> rsspad or rsspad /path/to/media/folder",
        bg_rgb=(0.04, 0.07, 0.12),
        border_rgb=(0.22, 0.74, 0.97)
    )

    # ------------------ SECTION: CINNAMON DESKTOP INTEGRATION ------------------
    builder.add_section_header("Linux Mint Cinnamon Integration")
    builder.add_2col_grid(
        [
            ("Panel Shortcut", "Right-click 'RSSpad' in the Cinnamon Menu (Sound &amp; Video / Favorites) and select 'Add to panel'."),
            ("Application Location", "Standard installation resides at /home/bluechile/rsspad with executable linked to ~/.local/bin/rsspad.")
        ],
        [
            ("Desktop Launcher", "A verified desktop shortcut is maintained at ~/Desktop/rsspad.desktop for instant double-click launch."),
            ("HiDPI Retina Icon", "Vector scalable SVG icon installed across 16px to 512px system icon themes.")
        ]
    )

    builder.finish()
    print(f"Generated compact manual: {output_pdf}")

if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else "/home/bluechile/Desktop/RSSpad User Manual.pdf"
    icon = sys.argv[2] if len(sys.argv) > 2 else "/home/bluechile/Videos/Daily Dean Blues Instrumentals/rsspad.svg"
    build_compact_manual(out_file, icon)

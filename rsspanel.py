#!/usr/bin/env python3
"""
RSSpanel - Podcast / RSS Feed Studio
Turns a folder of audio tracks into a podcast-compliant RSS feed, with live
folder watching, WAV -> MP3 conversion, track playback, feed preview,
a local LAN preview server, and one-click publishing.
Shares the PythonPanel dark neon aesthetic. Designed for Linux Mint Cinnamon.
"""

import os
import socket
import subprocess
import sys
import threading
import functools
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.dont_write_bytecode = True
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('GtkSource', '4')
gi.require_version('Pango', '1.0')

from gi.repository import Gtk, Gdk, GdkPixbuf, GtkSource, Pango, GLib, Gio

try:
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    Gst.init(None)
except (ValueError, ImportError):
    Gst = None

import feed_core
from feed_core import fmt_duration, fmt_size

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FOLDER = os.path.expanduser("~/Music")
SERVER_PORT = 8765

# Track list columns
COL_TITLE, COL_FILE, COL_FORMAT, COL_DURATION, COL_SIZE, COL_DATE, COL_PATH, COL_ICON = range(8)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class RSSpanelWindow(Gtk.ApplicationWindow):
    """Main application window for RSSpanel."""

    APP_NAME = "RSSpanel"
    APP_VERSION = "1.0"

    def __init__(self, app, initial_folder=None):
        super().__init__(application=app, title=self.APP_NAME)
        self.set_default_size(1180, 740)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.folder = None
        self.cfg = {}
        self.tracks = []
        self._monitor = None
        self._regen_timeout = None
        self._loading_form = False
        self._server = None
        self._player = None
        self._playing_path = None
        self._last_generated = None

        self.set_wmclass("rsspanel", "RSSpanel")
        self._set_icons()

        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", True)
        self._apply_dark_neon_theme()

        self._build_header_bar()
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(body)
        self.hpaned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.hpaned.pack1(self._build_sidebar(), False, False)
        self.hpaned.pack2(self._build_main_area(), True, False)
        self.hpaned.set_position(330)
        body.pack_start(self.hpaned, True, True, 0)
        body.pack_start(self._build_status_bar(), False, False, 0)
        self._setup_shortcuts()
        self._setup_drag_and_drop()
        self._init_player()

        self.connect("delete-event", self._on_delete_event)
        self.show_all()

        folder = initial_folder or self._load_last_folder() or (
            APP_DIR if os.path.isfile(os.path.join(APP_DIR, feed_core.CONFIG_NAME)) else DEFAULT_FOLDER
        )
        if os.path.isdir(folder):
            self.open_folder(folder)
        else:
            self.log("No feed folder open. Use the folder button to choose one.")
            self._update_status()

    # --------------------------------------------------------------------------
    # Look & feel (shared PythonPanel neon theme)
    # --------------------------------------------------------------------------
    def _set_icons(self):
        icon_path = os.path.join(APP_DIR, "rsspanel.svg")
        if not os.path.exists(icon_path):
            return
        try:
            Gtk.Window.set_default_icon_from_file(icon_path)
            pixbufs = [GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, sz, sz, True)
                       for sz in (16, 24, 32, 48, 64, 128, 256)]
            Gtk.Window.set_default_icon_list(pixbufs)
            self.set_icon_list(pixbufs)
        except GLib.Error:
            pass

    def _apply_dark_neon_theme(self):
        styles_dir = os.path.join(APP_DIR, "styles")
        if os.path.isdir(styles_dir):
            GtkSource.StyleSchemeManager.get_default().prepend_search_path(styles_dir)

        css = b"""
        /* RSSpanel Dark Neon Theme (PythonPanel family) */
        window, dialog, .background {
            background-color: #0b0f19;
            color: #ffffff;
        }
        headerbar {
            background: linear-gradient(to bottom, #111827, #0b0f19);
            border-bottom: 1px solid rgba(0, 240, 255, 0.35);
            box-shadow: 0 1px 6px rgba(0, 240, 255, 0.12);
            color: #ffffff;
            padding: 4px 6px;
        }
        headerbar .title { color: #ffffff; font-weight: bold; }
        headerbar .subtitle { color: #38bdf8; font-size: 85%; }

        button {
            background-color: #131d33;
            color: #ffffff;
            border: 1px solid rgba(0, 240, 255, 0.25);
            border-radius: 4px;
            padding: 4px 8px;
            transition: all 150ms ease;
        }
        button:hover {
            background-color: #1a2744;
            border-color: #00f0ff;
            color: #00f0ff;
            box-shadow: 0 0 6px rgba(0, 240, 255, 0.35);
        }
        button:checked, button:active {
            background-color: #034b75;
            border-color: #00f0ff;
            color: #ffffff;
            box-shadow: 0 0 8px rgba(0, 240, 255, 0.45);
        }
        button.neon-primary {
            background: linear-gradient(to bottom, #035a8c, #034b75);
            border-color: #00f0ff;
            font-weight: bold;
        }
        button.neon-primary:hover { color: #ffffff; box-shadow: 0 0 10px rgba(0, 240, 255, 0.6); }
        .linked > button { border-color: rgba(0, 240, 255, 0.25); }
        .linked > button:hover { border-color: #00f0ff; }

        notebook { background-color: #070a14; }
        notebook > header {
            background-color: #070a14;
            border-bottom: 1px solid rgba(0, 240, 255, 0.2);
        }
        notebook tab {
            background-color: #0b0f19;
            color: #94a3b8;
            border: 1px solid rgba(0, 240, 255, 0.15);
            border-bottom: none;
            padding: 5px 12px;
            margin-right: 2px;
            border-top-left-radius: 5px;
            border-top-right-radius: 5px;
        }
        notebook tab:hover {
            background-color: #131d33;
            color: #e0f2fe;
            border-color: rgba(0, 240, 255, 0.4);
        }
        notebook tab:checked {
            background-color: #0a0e1a;
            color: #ffffff;
            border-color: #00f0ff;
            border-top: 2px solid #00f0ff;
            box-shadow: inset 0 2px 0 #00f0ff;
        }
        notebook tab label { color: inherit; font-weight: 500; }

        paned > separator {
            background-color: #070a14;
            border: 1px solid rgba(0, 240, 255, 0.25);
            min-height: 4px;
            min-width: 4px;
        }
        paned > separator:hover {
            background-color: #00f0ff;
            box-shadow: 0 0 8px rgba(0, 240, 255, 0.6);
        }

        .sidebar-box {
            background-color: #080c16;
            border-right: 1px solid rgba(0, 240, 255, 0.25);
        }
        .sidebar-header {
            background-color: #0d1322;
            border-bottom: 1px solid rgba(0, 240, 255, 0.2);
        }
        .sidebar-title {
            color: #00f0ff;
            font-size: 85%;
            font-weight: bold;
            letter-spacing: 0.5px;
        }
        label.field-label { color: #7dd3fc; font-size: 88%; }
        label.hint { color: #64748b; font-size: 82%; }
        label.warn { color: #fbbf24; font-size: 85%; }
        label.feed-url { color: #00f0ff; font-family: monospace; }

        .detail-box {
            background-color: #0d1322;
            border-top: 1px solid rgba(0, 240, 255, 0.25);
        }

        .statusbar, #statusbar {
            background-color: #070a14;
            border-top: 1px solid rgba(0, 240, 255, 0.2);
            color: #94a3b8;
            padding: 2px 8px;
        }
        .statusbar label, #statusbar label { color: #cbd5e1; font-size: 88%; }
        label.status-live { color: #00f0ff; font-weight: bold; }

        entry, spinbutton {
            background-color: #0a0e1a;
            color: #ffffff;
            border: 1px solid rgba(0, 240, 255, 0.3);
            border-radius: 4px;
            padding: 4px 8px;
        }
        entry:focus {
            border-color: #00f0ff;
            box-shadow: 0 0 5px rgba(0, 240, 255, 0.4);
        }
        textview, textview text { background-color: #0a0e1a; color: #ffffff; }
        frame > border { border: 1px solid rgba(0, 240, 255, 0.25); }

        switch { background-color: #131d33; border: 1px solid rgba(0, 240, 255, 0.3); }
        switch:checked { background-color: #034b75; border-color: #00f0ff; }
        switch slider { background-color: #e0f2fe; }

        menu, .menu, popover {
            background-color: #0d1322;
            color: #ffffff;
            border: 1px solid rgba(0, 240, 255, 0.35);
            padding: 4px;
        }
        menuitem { color: #e0f2fe; padding: 4px 10px; }
        menuitem:hover { background-color: #034b75; color: #ffffff; }
        menuitem:disabled { color: #475569; }

        treeview {
            background-color: #0a0e1a;
            color: #f8fafc;
            border: none;
        }
        treeview:selected { background-color: #034b75; color: #ffffff; }
        treeview header button {
            background-color: #0d1322;
            color: #00f0ff;
            border-bottom: 1px solid rgba(0, 240, 255, 0.3);
            font-weight: bold;
        }

        scrollbar { background-color: #070a14; }
        scrollbar slider {
            background-color: #1e293b;
            border-radius: 4px;
            min-width: 8px;
            min-height: 8px;
        }
        scrollbar slider:hover { background-color: #0284c7; }
        scrollbar slider:active { background-color: #00f0ff; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # --------------------------------------------------------------------------
    # Header Bar
    # --------------------------------------------------------------------------
    def _icon_button(self, icon, tooltip, callback, toggle=False):
        btn = Gtk.ToggleButton() if toggle else Gtk.Button()
        btn.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
        btn.set_tooltip_text(tooltip)
        btn.connect("toggled" if toggle else "clicked", callback)
        return btn

    def _build_header_bar(self):
        self.header = Gtk.HeaderBar()
        self.header.set_show_close_button(True)
        self.header.set_title(self.APP_NAME)
        self.header.set_subtitle("Podcast & RSS Feed Studio")
        self.set_titlebar(self.header)

        left = Gtk.Box(spacing=0)
        left.get_style_context().add_class("linked")
        self.btn_sidebar = self._icon_button(
            "sidebar-show-symbolic", "Toggle Feed Settings Sidebar (Ctrl+B)",
            lambda w: hasattr(self, "sidebar") and self.sidebar.set_visible(w.get_active()), toggle=True)
        self.btn_sidebar.set_active(True)
        left.pack_start(self.btn_sidebar, False, False, 0)
        left.pack_start(self._icon_button(
            "folder-open-symbolic", "Open Feed Folder (Ctrl+O)",
            lambda w: self.on_open_folder()), False, False, 0)
        left.pack_start(self._icon_button(
            "list-add-symbolic", "Add Tracks to Feed (Ctrl+I)",
            lambda w: self.on_add_tracks()), False, False, 0)
        left.pack_start(self._icon_button(
            "view-refresh-symbolic", "Rescan Folder (Ctrl+R)",
            lambda w: self.refresh()), False, False, 0)
        self.header.pack_start(left)

        self.header.pack_end(self._build_menu_button())

        # Generate / Publish group
        pub = Gtk.Box(spacing=0)
        pub.get_style_context().add_class("linked")
        self.btn_generate = Gtk.Button()
        gen_box = Gtk.Box(spacing=6)
        gen_box.pack_start(Gtk.Image.new_from_icon_name("document-save-symbolic", Gtk.IconSize.BUTTON), False, False, 0)
        gen_box.pack_start(Gtk.Label(label="Generate Feed"), False, False, 0)
        self.btn_generate.add(gen_box)
        self.btn_generate.get_style_context().add_class("neon-primary")
        self.btn_generate.set_tooltip_text("Write feed.xml (F5 / Ctrl+S)")
        self.btn_generate.connect("clicked", lambda w: self.generate_feed())
        pub.pack_start(self.btn_generate, False, False, 0)
        pub.pack_start(self._icon_button(
            "send-to-symbolic", "Generate & Publish (F6) - runs your publish command",
            lambda w: self.publish()), False, False, 0)
        self.header.pack_end(pub)

        # LAN preview server toggle
        self.btn_server = self._icon_button(
            "network-wireless-symbolic", "Serve folder on your LAN for testing in a podcast app",
            self._on_server_toggled, toggle=True)
        self.header.pack_end(self.btn_server)

        # Playback group
        play = Gtk.Box(spacing=0)
        play.get_style_context().add_class("linked")
        self.btn_play = self._icon_button(
            "media-playback-start-symbolic", "Play Selected Track (Space)",
            lambda w: self.toggle_play())
        play.pack_start(self.btn_play, False, False, 0)
        play.pack_start(self._icon_button(
            "media-playback-stop-symbolic", "Stop Playback", lambda w: self.stop_playback()),
            False, False, 0)
        self.header.pack_end(play)

    def _build_menu_button(self):
        menu_button = Gtk.MenuButton()
        menu_button.set_image(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        menu_button.set_tooltip_text("Menu and Tools")
        menu = Gtk.Menu()

        def add(label, cb, parent=menu):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda w: cb())
            parent.append(item)
            return item

        add("Open Feed Folder... (Ctrl+O)", self.on_open_folder)
        add("Add Tracks... (Ctrl+I)", self.on_add_tracks)
        add("Open Folder in File Manager", lambda: self._xdg_open(self.folder))
        menu.append(Gtk.SeparatorMenuItem())

        conv_item = Gtk.MenuItem(label="Media & Cover Tools")
        conv_menu = Gtk.Menu()
        add("Generate Cover Art from Video (cover.jpg)", self.generate_cover_art, conv_menu)
        add("Extract MP3 Audio from Selected Video/WAV", lambda: self.convert_to_mp3(selected_only=True), conv_menu)
        add("Extract MP3 Audio from All Videos/WAVs", lambda: self.convert_to_mp3(selected_only=False), conv_menu)
        conv_item.set_submenu(conv_menu)
        menu.append(conv_item)

        add("Rename / Remove Selected Track...", self.on_remove_track)
        menu.append(Gtk.SeparatorMenuItem())

        add("Sync & Publish to GitHub (F6)", self.publish)
        add("Copy Feed URL (Ctrl+Shift+C)", self.copy_feed_url)
        add("Use LAN Server as Base URL", self.use_lan_base_url)
        add("Open feed.xml in Browser", lambda: self._xdg_open(self._feed_path()))
        menu.append(Gtk.SeparatorMenuItem())
        add("Keyboard Shortcuts", self.show_shortcuts)
        add("About RSSpanel", self.show_about)
        add("Quit (Ctrl+Q)", self.close)

        menu.show_all()
        menu_button.set_popup(menu)
        return menu_button

    # --------------------------------------------------------------------------
    # Sidebar: feed settings
    # --------------------------------------------------------------------------
    def _build_sidebar(self):
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sidebar.get_style_context().add_class("sidebar-box")
        self.sidebar.set_size_request(280, -1)

        hdr = Gtk.Box(spacing=6)
        hdr.get_style_context().add_class("sidebar-header")
        hdr.set_border_width(6)
        title = Gtk.Label(label="FEED SETTINGS", xalign=0)
        title.get_style_context().add_class("sidebar-title")
        hdr.pack_start(title, True, True, 4)
        self.sidebar.pack_start(hdr, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        grid.set_border_width(12)
        scroller.add(grid)
        self.sidebar.pack_start(scroller, True, True, 0)

        self.fields = {}

        def field(key, label, hint=None, multiline=False):
            lbl = Gtk.Label(label=label, xalign=0)
            lbl.get_style_context().add_class("field-label")
            lbl.set_margin_top(8)
            grid.pack_start(lbl, False, False, 0)
            if multiline:
                tv = Gtk.TextView()
                tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
                tv.set_left_margin(6); tv.set_right_margin(6)
                tv.set_top_margin(4); tv.set_bottom_margin(4)
                tv.get_buffer().connect("changed", lambda b: self._on_field_changed())
                frame = Gtk.Frame()
                frame.set_size_request(-1, 70)
                frame.add(tv)
                grid.pack_start(frame, False, False, 0)
                self.fields[key] = tv
            else:
                ent = Gtk.Entry()
                ent.connect("changed", lambda e: self._on_field_changed())
                grid.pack_start(ent, False, False, 0)
                self.fields[key] = ent
            if hint:
                h = Gtk.Label(label=hint, xalign=0)
                h.set_line_wrap(True)
                h.get_style_context().add_class("hint")
                grid.pack_start(h, False, False, 0)

        field("base_url", "Public Base URL", "Where this folder's files are hosted online.")
        self.lbl_url_warn = Gtk.Label(xalign=0)
        self.lbl_url_warn.set_line_wrap(True)
        self.lbl_url_warn.get_style_context().add_class("warn")
        self.lbl_url_warn.set_no_show_all(True)
        grid.pack_start(self.lbl_url_warn, False, False, 0)
        field("title", "Feed Title")
        field("description", "Description", multiline=True)
        field("author", "Author / Artist")
        field("image_url", "Cover Art URL", "Square JPG/PNG, 1400-3000 px, hosted online.")
        field("category", "Category")
        field("language", "Language")
        field("github_repo", "GitHub Repository (owner/repo)",
              "Uploads >95 MB video/audio to GitHub Releases & publishes feed to Pages.")
        field("mp3_bitrate", "MP3 Bitrate (conversion)")
        field("publish_command", "Custom Publish Command (optional)",
              "Leave blank when GitHub Repository is set above, or set a custom shell command.")

        def switch_row(key, label):
            row = Gtk.Box(spacing=8)
            row.set_margin_top(10)
            lbl = Gtk.Label(label=label, xalign=0)
            lbl.get_style_context().add_class("field-label")
            sw = Gtk.Switch()
            sw.connect("notify::active", lambda *a: self._on_field_changed())
            row.pack_start(lbl, True, True, 0)
            row.pack_end(sw, False, False, 0)
            grid.pack_start(row, False, False, 0)
            self.fields[key] = sw

        switch_row("explicit", "Explicit Content")
        switch_row("auto_generate", "Auto-generate on Folder Change")

        url_lbl = Gtk.Label(label="Feed URL", xalign=0)
        url_lbl.get_style_context().add_class("field-label")
        url_lbl.set_margin_top(14)
        grid.pack_start(url_lbl, False, False, 0)
        self.lbl_feed_url = Gtk.Label(xalign=0, selectable=True)
        self.lbl_feed_url.set_line_wrap(True)
        self.lbl_feed_url.set_line_wrap_mode(Pango.WrapMode.CHAR)
        self.lbl_feed_url.get_style_context().add_class("feed-url")
        grid.pack_start(self.lbl_feed_url, False, False, 0)
        return self.sidebar

    def _get_field(self, key):
        w = self.fields[key]
        if isinstance(w, Gtk.Switch):
            return w.get_active()
        if isinstance(w, Gtk.TextView):
            b = w.get_buffer()
            return b.get_text(b.get_start_iter(), b.get_end_iter(), False).strip()
        return w.get_text().strip()

    def _set_field(self, key, value):
        w = self.fields[key]
        if isinstance(w, Gtk.Switch):
            w.set_active(bool(value))
        elif isinstance(w, Gtk.TextView):
            w.get_buffer().set_text(value or "")
        else:
            w.set_text(value or "")

    def _load_form(self):
        self._loading_form = True
        for key in self.fields:
            self._set_field(key, self.cfg.get(key))
        self._loading_form = False
        self._update_url_hints()

    def _on_field_changed(self):
        if self._loading_form or not self.folder:
            return
        for key in self.fields:
            self.cfg[key] = self._get_field(key)
        self._save_cfg()
        self._update_url_hints()
        self._schedule_regen(delay=1200)

    def _update_url_hints(self):
        base = (self.cfg.get("base_url") or "").strip()
        warn = None
        if not base or "yourdomain.com" in base:
            warn = "Set this to your real hosting URL before subscribing in a podcast app."
        elif not base.startswith(("http://", "https://")):
            warn = "Base URL should start with https://"
        self.lbl_url_warn.set_text(warn or "")
        self.lbl_url_warn.set_visible(bool(warn))
        self.lbl_feed_url.set_text(self._feed_url() or "-")

    def _feed_url(self):
        base = (self.cfg.get("base_url") or "").rstrip("/")
        return f"{base}/{self.cfg.get('output_name') or 'feed.xml'}" if base else ""

    def _feed_path(self):
        if not self.folder:
            return None
        return os.path.join(self.folder, self.cfg.get("output_name") or "feed.xml")

    # --------------------------------------------------------------------------
    # Main area: Tracks / feed.xml / Log
    # --------------------------------------------------------------------------
    def _build_main_area(self):
        self.notebook = Gtk.Notebook()
        self.notebook.append_page(self._build_tracks_page(), self._tab_label("audio-x-generic-symbolic", "Tracks"))
        self.notebook.append_page(self._build_xml_page(), self._tab_label("text-x-generic-symbolic", "feed.xml"))
        self.notebook.append_page(self._build_log_page(), self._tab_label("utilities-terminal-symbolic", "Activity Log"))
        self.notebook.connect("switch-page", self._on_switch_page)
        return self.notebook

    @staticmethod
    def _tab_label(icon, text):
        box = Gtk.Box(spacing=6)
        box.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU), False, False, 0)
        box.pack_start(Gtk.Label(label=text), False, False, 0)
        box.show_all()
        return box

    def _build_tracks_page(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.store = Gtk.ListStore(str, str, str, str, str, str, str, str)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_enable_search(True)
        self.tree.set_search_column(COL_TITLE)

        icon_r = Gtk.CellRendererPixbuf()
        col = Gtk.TreeViewColumn("", icon_r, icon_name=COL_ICON)
        col.set_min_width(28)
        self.tree.append_column(col)

        def text_col(title, idx, expand=False, mono=False, color=None):
            r = Gtk.CellRendererText()
            r.set_padding(6, 5)
            if mono:
                r.set_property("family", "monospace")
            if color:
                r.set_property("foreground", color)
            if expand:
                r.set_property("ellipsize", Pango.EllipsizeMode.END)
            c = Gtk.TreeViewColumn(title, r, text=idx)
            c.set_resizable(True)
            c.set_expand(expand)
            c.set_sort_column_id(idx)
            self.tree.append_column(c)

        text_col("Title", COL_TITLE, expand=True)
        text_col("File", COL_FILE, expand=True, color="#94a3b8")
        text_col("Format", COL_FORMAT, color="#38bdf8")
        text_col("Length", COL_DURATION, mono=True)
        text_col("Size", COL_SIZE, mono=True)
        text_col("Published", COL_DATE, color="#7dd3fc")

        self.tree.get_selection().connect("changed", self._on_track_selected)
        self.tree.connect("row-activated", lambda *a: self.toggle_play(force_play=True))

        sw = Gtk.ScrolledWindow()
        sw.add(self.tree)
        vbox.pack_start(sw, True, True, 0)

        # Empty-state hint overlay label
        self.lbl_empty = Gtk.Label()
        self.lbl_empty.set_markup(
            "<span foreground='#38bdf8' size='large'>Drop audio files here</span>\n"
            "<span foreground='#64748b'>or use  +  to add tracks to this feed</span>")
        self.lbl_empty.set_justify(Gtk.Justification.CENTER)
        self.lbl_empty.set_no_show_all(True)
        vbox.pack_start(self.lbl_empty, True, True, 0)

        # Per-track detail editor
        detail = Gtk.Grid(column_spacing=10, row_spacing=6)
        detail.get_style_context().add_class("detail-box")
        detail.set_border_width(10)
        hdr = Gtk.Label(label="EPISODE DETAILS", xalign=0)
        hdr.get_style_context().add_class("sidebar-title")
        detail.attach(hdr, 0, 0, 2, 1)
        for row, (label, attr) in enumerate((("Episode Title", "ent_track_title"),
                                              ("Description", "ent_track_desc")), start=1):
            lbl = Gtk.Label(label=label, xalign=1)
            lbl.get_style_context().add_class("field-label")
            ent = Gtk.Entry(hexpand=True)
            ent.connect("activate", lambda e: self._save_track_details())
            setattr(self, attr, ent)
            detail.attach(lbl, 0, row, 1, 1)
            detail.attach(ent, 1, row, 1, 1)
        btns = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        b_reset = Gtk.Button(label="Reset to Default")
        b_reset.connect("clicked", lambda w: self._save_track_details(reset=True))
        b_apply = Gtk.Button(label="Apply")
        b_apply.get_style_context().add_class("neon-primary")
        b_apply.connect("clicked", lambda w: self._save_track_details())
        btns.pack_start(b_reset, False, False, 0)
        btns.pack_start(b_apply, False, False, 0)
        detail.attach(btns, 1, 3, 1, 1)
        self.detail_box = detail
        detail.set_sensitive(False)
        vbox.pack_start(detail, False, False, 0)
        return vbox

    def _build_xml_page(self):
        self.xml_buffer = GtkSource.Buffer()
        lang = GtkSource.LanguageManager.get_default().get_language("xml")
        if lang:
            self.xml_buffer.set_language(lang)
        scheme_mgr = GtkSource.StyleSchemeManager.get_default()
        scheme = scheme_mgr.get_scheme("pythonpanel-neon") or scheme_mgr.get_scheme("oblivion")
        if scheme:
            self.xml_buffer.set_style_scheme(scheme)
        view = GtkSource.View(buffer=self.xml_buffer)
        view.set_editable(False)
        view.set_show_line_numbers(True)
        view.set_highlight_current_line(True)
        view.set_monospace(True)
        view.set_left_margin(6)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        sw = Gtk.ScrolledWindow()
        sw.add(view)
        return sw

    def _build_log_page(self):
        self.log_view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        self.log_view.set_left_margin(10)
        self.log_view.set_top_margin(6)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        buf = self.log_view.get_buffer()
        buf.create_tag("time", foreground="#38bdf8")
        buf.create_tag("error", foreground="#f43f5e")
        buf.create_tag("ok", foreground="#00f0ff")
        sw = Gtk.ScrolledWindow()
        sw.add(self.log_view)
        return sw

    def _build_status_bar(self):
        bar = Gtk.Box(spacing=18)
        bar.set_name("statusbar")
        bar.get_style_context().add_class("statusbar")
        self.lbl_status_tracks = Gtk.Label(xalign=0)
        self.lbl_status_gen = Gtk.Label(xalign=0)
        self.lbl_status_play = Gtk.Label(xalign=0)
        self.lbl_status_server = Gtk.Label(xalign=1)
        self.lbl_status_server.set_selectable(True)
        bar.pack_start(self.lbl_status_tracks, False, False, 0)
        bar.pack_start(self.lbl_status_gen, False, False, 0)
        bar.pack_start(self.lbl_status_play, True, True, 0)
        bar.pack_end(self.lbl_status_server, False, False, 0)
        return bar

    # --------------------------------------------------------------------------
    # Folder handling
    # --------------------------------------------------------------------------
    def open_folder(self, folder):
        folder = os.path.abspath(os.path.expanduser(folder))
        if not os.path.isdir(folder):
            self.error_dialog("Folder not found", folder)
            return
        self.stop_playback()
        self.folder = folder
        self.cfg = feed_core.load_config(Path(folder))
        if not os.path.exists(os.path.join(folder, feed_core.CONFIG_NAME)):
            self._save_cfg()
        self.header.set_subtitle(folder.replace(os.path.expanduser("~"), "~", 1))
        self._load_form()
        self._watch_folder()
        self._save_last_folder(folder)
        self.log(f"Opened feed folder: {folder}")
        self.refresh()
        self._load_xml_preview()
        if self._server:
            self._stop_server()
            self._start_server()

    def _save_cfg(self):
        if self.folder:
            try:
                feed_core.save_config(Path(self.folder), self.cfg)
            except OSError as exc:
                self.log(f"Could not save settings: {exc}", "error")

    def _watch_folder(self):
        if self._monitor:
            self._monitor.cancel()
        if hasattr(self, "_sub_monitor") and self._sub_monitor:
            self._sub_monitor.cancel()
            self._sub_monitor = None
        try:
            self._monitor = Gio.File.new_for_path(self.folder).monitor_directory(
                Gio.FileMonitorFlags.WATCH_MOVES, None)
            self._monitor.connect("changed", self._on_folder_changed)
            for sub in ("tracks", "media", "episodes"):
                subdir = Path(self.folder) / sub
                if subdir.is_dir():
                    self._sub_monitor = Gio.File.new_for_path(str(subdir)).monitor_directory(
                        Gio.FileMonitorFlags.WATCH_MOVES, None)
                    self._sub_monitor.connect("changed", self._on_folder_changed)
                    break
        except GLib.Error as exc:
            self.log(f"Folder watching unavailable: {exc.message}", "error")

    def _on_folder_changed(self, _mon, file, _other, _event):
        name = file.get_basename() or ""
        if name.startswith(".") or name in (self.cfg.get("output_name") or "feed.xml", "index.html", "cover.jpg"):
            return
        if Path(name).suffix.lower() not in feed_core.MIME_TYPES:
            return
        self._schedule_regen(delay=2000, from_watch=True)

    def _schedule_regen(self, delay=1500, from_watch=False):
        if self._regen_timeout:
            GLib.source_remove(self._regen_timeout)

        def fire():
            self._regen_timeout = None
            self.refresh(quiet=True)
            if self.cfg.get("auto_generate"):
                self.generate_feed(quiet=not from_watch)
            return False

        self._regen_timeout = GLib.timeout_add(delay, fire)

    def refresh(self, quiet=False):
        if not self.folder:
            return
        selected = self._selected_path()
        try:
            self.tracks = feed_core.scan_folder(Path(self.folder), self.cfg)
        except OSError as exc:
            self.log(f"Scan failed: {exc}", "error")
            return
        self.store.clear()
        for t in self.tracks:
            fmt = t.path.suffix.lstrip(".").upper()
            if t.alternates:
                fmt += " (+" + ", ".join(a.suffix.lstrip(".").upper() for a in t.alternates) + ")"
            playing = self._playing_path == str(t.path)
            default_icon = "video-x-generic-symbolic" if t.is_video else "audio-x-generic-symbolic"
            self.store.append([
                t.title, t.name, fmt, fmt_duration(t.duration), fmt_size(t.size),
                datetime.fromtimestamp(t.mtime).strftime("%b %d, %Y  %H:%M"),
                str(t.path),
                "media-playback-start-symbolic" if playing else default_icon,
            ])
        if selected:
            self._select_path(selected)
        has = bool(self.tracks)
        self.tree.get_parent().set_visible(has)
        self.lbl_empty.set_visible(not has)
        if not quiet:
            self.log(f"Scanned {len(self.tracks)} track(s).")
        self._update_status()

    # --------------------------------------------------------------------------
    # Feed generation & publishing
    # --------------------------------------------------------------------------
    def generate_feed(self, quiet=False):
        if not self.folder:
            self.on_open_folder()
            return None
        try:
            out = feed_core.write_feed(Path(self.folder), self.cfg)
            self.tracks = feed_core.scan_folder(Path(self.folder), self.cfg)
        except OSError as exc:
            self.log(f"Feed generation failed: {exc}", "error")
            self.error_dialog("Feed generation failed", str(exc))
            return None
        self._last_generated = datetime.now()
        self._load_xml_preview()
        self._update_status()
        self.log(f"Generated {out.name} with {len(self.tracks)} track(s).", "ok")
        if not quiet:
            self._flash_status(f"feed.xml written - {len(self.tracks)} tracks")
        return out

    def publish(self):
        if not self.generate_feed():
            return
        cmd = (self.cfg.get("publish_command") or "").strip()
        repo = (self.cfg.get("github_repo") or "").strip()
        if not cmd and repo:
            self.log(f"Syncing media & feed to GitHub ({repo})...")
            self.notebook.set_current_page(2)
            def on_gh_done(_code):
                self.cfg = feed_core.load_config(Path(self.folder))
                self._load_form()
                self.refresh(quiet=True)
                self._load_xml_preview()
            self._run_async(
                [sys.executable, "-B", os.path.join(APP_DIR, "feed_core.py"), "--sync-github", self.folder],
                "GitHub Sync", cwd=self.folder, on_done=on_gh_done)
            return
        if not cmd:
            self.info_dialog(
                "No publish target set",
                "feed.xml has been generated.\n\nTo upload automatically, set a GitHub Repository "
                "(owner/repo) or a Custom Publish Command in the Feed Settings sidebar.")
            return
        self.log(f"$ {cmd}")
        self.notebook.set_current_page(2)
        self._run_async(["bash", "-lc", cmd], "Publish", cwd=self.folder)

    def _run_async(self, argv, label, cwd=None, on_done=None):
        def worker():
            try:
                proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True)
                for line in proc.stdout:
                    GLib.idle_add(self.log, line.rstrip())
                code = proc.wait()
            except OSError as exc:
                GLib.idle_add(self.log, f"{label} failed: {exc}", "error")
                code = -1
            GLib.idle_add(self._async_done, label, code, on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _async_done(self, label, code, on_done):
        if code == 0:
            self.log(f"{label} finished successfully.", "ok")
            self._flash_status(f"{label} complete")
        else:
            self.log(f"{label} exited with code {code}.", "error")
            self._flash_status(f"{label} failed (code {code})")
        if on_done:
            on_done(code)
        return False

    def _load_xml_preview(self):
        path = self._feed_path()
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                self.xml_buffer.set_text(f.read())
        else:
            self.xml_buffer.set_text("<!-- feed.xml has not been generated yet. Press F5. -->")

    # --------------------------------------------------------------------------
    # Tracks: add, edit, convert, remove
    # --------------------------------------------------------------------------
    def _selected_path(self):
        model, it = self.tree.get_selection().get_selected()
        return model[it][COL_PATH] if it else None

    def _select_path(self, path):
        for row in self.store:
            if row[COL_PATH] == path:
                self.tree.get_selection().select_iter(row.iter)
                return

    def _track_for(self, path):
        return next((t for t in self.tracks if str(t.path) == path), None)

    def _on_track_selected(self, _sel):
        t = self._track_for(self._selected_path() or "")
        self.detail_box.set_sensitive(t is not None)
        self.ent_track_title.set_text(t.title if t else "")
        self.ent_track_desc.set_text(t.description if t else "")

    def _save_track_details(self, reset=False):
        t = self._track_for(self._selected_path() or "")
        if not t:
            return
        overrides = self.cfg.setdefault("tracks", {})
        if reset:
            overrides.pop(t.name, None)
        else:
            existing = overrides.get(t.name, {})
            existing.update({"title": self.ent_track_title.get_text().strip(),
                             "description": self.ent_track_desc.get_text().strip()})
            overrides[t.name] = existing
        self._save_cfg()
        self.refresh(quiet=True)
        self._on_track_selected(None)
        self.log(f"Updated episode details for {t.name}.")
        if self.cfg.get("auto_generate"):
            self.generate_feed(quiet=True)

    def on_add_tracks(self):
        if not self.folder:
            self.on_open_folder()
            if not self.folder:
                return
        dlg = Gtk.FileChooserDialog(title="Add Tracks to Feed", parent=self,
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Add", Gtk.ResponseType.OK)
        dlg.set_select_multiple(True)
        flt = Gtk.FileFilter()
        flt.set_name("Video & Audio files")
        for ext in feed_core.MIME_TYPES:
            flt.add_pattern(f"*{ext}")
            flt.add_pattern(f"*{ext.upper()}")
        dlg.add_filter(flt)
        files = dlg.get_filenames() if dlg.run() == Gtk.ResponseType.OK else []
        dlg.destroy()
        self.import_files(files)

    def import_files(self, files):
        files = [f for f in files if Path(f).suffix.lower() in feed_core.MIME_TYPES]
        if not files or not self.folder:
            return
        dest_dir = Path(self.folder)
        if (dest_dir / "tracks").is_dir():
            dest_dir = dest_dir / "tracks"
        elif (dest_dir / "media").is_dir():
            dest_dir = dest_dir / "media"

        def worker():
            for src in files:
                src = Path(src)
                if src.parent.resolve() == dest_dir.resolve():
                    continue
                dst = dest_dir / src.name
                n = 2
                while dst.exists():
                    dst = dest_dir / f"{src.stem} ({n}){src.suffix}"
                    n += 1
                try:
                    shutil_copy(src, dst)
                    GLib.idle_add(self.log, f"Added {dst.name}", "ok")
                except OSError as exc:
                    GLib.idle_add(self.log, f"Could not add {src.name}: {exc}", "error")
            GLib.idle_add(self._schedule_regen, 300, True)

        self.log(f"Importing {len(files)} file(s)...")
        threading.Thread(target=worker, daemon=True).start()

    def generate_cover_art(self):
        if not self.folder:
            return
        if not shutil_which("ffmpeg"):
            self.error_dialog("ffmpeg not found", "Install it with:  sudo apt install ffmpeg")
            return
        t = self._track_for(self._selected_path() or "")
        video = t.path if (t and t.is_video) else next((x.path for x in self.tracks if x.is_video), None)
        if not video:
            self.info_dialog("No video found", "Add an MP4/MOV video track first to extract cover art.")
            return
        out = Path(self.folder) / "cover.jpg"
        res = subprocess.run(feed_core.make_cover_command(video, out), capture_output=True, text=True, check=False)
        if res.returncode == 0 and out.exists():
            base = (self.cfg.get("base_url") or "").rstrip("/")
            if base and "yourdomain.com" not in base:
                self._set_field("image_url", f"{base}/cover.jpg")
            self.log(f"Generated square podcast cover art: {out.name} ({fmt_size(out.stat().st_size)})", "ok")
            self._flash_status("cover.jpg generated")
        else:
            self.log(f"Cover art failed: {res.stderr.strip()}", "error")

    def convert_to_mp3(self, selected_only=True):
        if not shutil_which("ffmpeg"):
            self.error_dialog("ffmpeg not found", "Install it with:  sudo apt install ffmpeg")
            return
        if selected_only:
            t = self._track_for(self._selected_path() or "")
            targets = [t] if t else []
        else:
            targets = list(self.tracks)
        sources = [t.path for t in targets if t and t.path.suffix.lower() in (".wav", ".mp4", ".m4v", ".mov")]
        if not sources:
            self.info_dialog("Nothing to convert",
                             "Select a WAV or MP4 track first.")
            return
        bitrate = self.cfg.get("mp3_bitrate") or "192k"
        self.notebook.set_current_page(2)
        self.log(f"Extracting MP3 audio for {len(sources)} file(s) at {bitrate}...")

        def worker():
            for src in sources:
                GLib.idle_add(self.log, f"  {src.name} -> {src.stem}.mp3")
                mtime = src.stat().st_mtime
                res = subprocess.run(feed_core.extract_mp3_command(src, bitrate),
                                     capture_output=True, text=True, check=False)
                if res.returncode == 0:
                    dst = src.with_suffix(".mp3")
                    os.utime(dst, (mtime, mtime))  # keep original publish date
                    GLib.idle_add(self.log, f"  Done: {dst.name} ({fmt_size(dst.stat().st_size)})", "ok")
                else:
                    GLib.idle_add(self.log, f"  Failed: {res.stderr.strip()}", "error")
            GLib.idle_add(self.log, "Audio extraction complete.", "ok")
            GLib.idle_add(self._schedule_regen, 300, True)

        threading.Thread(target=worker, daemon=True).start()

    def on_remove_track(self):
        t = self._track_for(self._selected_path() or "")
        if not t:
            self.info_dialog("No track selected", "Select a track in the list first.")
            return
        dlg = Gtk.Dialog(title="Rename / Remove Track", transient_for=self, modal=True)
        dlg.add_buttons("Move to Trash", 1, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        "Rename", Gtk.ResponseType.OK)
        box = dlg.get_content_area()
        box.set_border_width(12)
        box.set_spacing(8)
        box.add(Gtk.Label(label="File name (without extension):", xalign=0))
        ent = Gtk.Entry(text=t.path.stem, activates_default=True)
        dlg.set_default_response(Gtk.ResponseType.OK)
        box.add(ent)
        if t.alternates:
            box.add(Gtk.Label(label=f"Also applies to: {', '.join(a.name for a in t.alternates)}", xalign=0))
        dlg.show_all()
        resp = dlg.run()
        new_stem = ent.get_text().strip()
        dlg.destroy()
        files = [t.path] + t.alternates
        try:
            if resp == 1:
                for f in files:
                    Gio.File.new_for_path(str(f)).trash(None)
                self.log(f"Moved to trash: {', '.join(f.name for f in files)}")
            elif resp == Gtk.ResponseType.OK and new_stem and new_stem != t.path.stem:
                ov = self.cfg.get("tracks", {})
                for f in files:
                    new = f.with_name(new_stem + f.suffix)
                    if new.exists():
                        raise OSError(f"{new.name} already exists")
                    f.rename(new)
                    if f.name in ov:
                        ov[new.name] = ov.pop(f.name)
                self._save_cfg()
                self.log(f"Renamed {t.path.stem} -> {new_stem}")
            else:
                return
        except (OSError, GLib.Error) as exc:
            self.error_dialog("Operation failed", str(exc))
            return
        if self._playing_path in [str(f) for f in files]:
            self.stop_playback()
        self._schedule_regen(200, True)

    # --------------------------------------------------------------------------
    # Playback (GStreamer)
    # --------------------------------------------------------------------------
    def _init_player(self):
        if Gst is None:
            return
        self._player = Gst.ElementFactory.make("playbin", "rsspanel-player")
        if self._player:
            bus = self._player.get_bus()
            bus.add_signal_watch()
            bus.connect("message::eos", lambda *a: self.stop_playback())
            bus.connect("message::error", self._on_player_error)
            GLib.timeout_add(500, self._update_play_position)

    def toggle_play(self, force_play=False):
        if self._player is None:
            path = self._selected_path()
            if path:
                self._xdg_open(path)
            return
        path = self._selected_path() or (self.tracks and str(self.tracks[0].path))
        if not path:
            return
        _, state, _ = self._player.get_state(0)
        if path == self._playing_path and not force_play:
            if state == Gst.State.PLAYING:
                self._player.set_state(Gst.State.PAUSED)
                self.btn_play.set_image(Gtk.Image.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.BUTTON))
            else:
                self._player.set_state(Gst.State.PLAYING)
                self.btn_play.set_image(Gtk.Image.new_from_icon_name("media-playback-pause-symbolic", Gtk.IconSize.BUTTON))
            return
        self._player.set_state(Gst.State.NULL)
        self._player.set_property("uri", Gio.File.new_for_path(path).get_uri())
        self._player.set_state(Gst.State.PLAYING)
        self._playing_path = path
        self.btn_play.set_image(Gtk.Image.new_from_icon_name("media-playback-pause-symbolic", Gtk.IconSize.BUTTON))
        self._refresh_play_icons()

    def stop_playback(self):
        if self._player:
            self._player.set_state(Gst.State.NULL)
        self._playing_path = None
        self.btn_play.set_image(Gtk.Image.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.BUTTON))
        self.lbl_status_play.set_text("")
        self._refresh_play_icons()

    def _refresh_play_icons(self):
        for row in self.store:
            ext = Path(row[COL_PATH]).suffix.lower()
            def_icon = "video-x-generic-symbolic" if ext in feed_core.VIDEO_EXTS else "audio-x-generic-symbolic"
            row[COL_ICON] = ("media-playback-start-symbolic" if row[COL_PATH] == self._playing_path
                             else def_icon)

    def _update_play_position(self):
        if self._player and self._playing_path:
            ok_p, pos = self._player.query_position(Gst.Format.TIME)
            ok_d, dur = self._player.query_duration(Gst.Format.TIME)
            if ok_p and ok_d:
                t = self._track_for(self._playing_path)
                name = t.title if t else os.path.basename(self._playing_path)
                self.lbl_status_play.set_text(
                    f"\u266b  {name}   {fmt_duration(pos / Gst.SECOND) if pos else '00:00'} / "
                    f"{fmt_duration(dur / Gst.SECOND)}")
        return True

    def _on_player_error(self, _bus, msg):
        err, _dbg = msg.parse_error()
        self.log(f"Playback error: {err.message}", "error")
        self.stop_playback()

    # --------------------------------------------------------------------------
    # LAN preview server
    # --------------------------------------------------------------------------
    @staticmethod
    def _lan_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"
        finally:
            s.close()

    def _lan_base(self):
        return f"http://{self._lan_ip()}:{SERVER_PORT}"

    def _on_server_toggled(self, btn):
        if btn.get_active():
            if not self._start_server():
                btn.set_active(False)
        else:
            self._stop_server()

    def _start_server(self):
        if not self.folder:
            return False
        handler = functools.partial(_QuietHandler, directory=self.folder)
        try:
            self._server = ThreadingHTTPServer(("0.0.0.0", SERVER_PORT), handler)
        except OSError as exc:
            self.error_dialog("Could not start LAN server", str(exc))
            self._server = None
            return False
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.log(f"LAN server running at {self._lan_base()}/  (Menu > Use LAN Server as Base URL "
                 f"to test the feed on a phone on the same Wi-Fi).", "ok")
        self._update_status()
        return True

    def _stop_server(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self.log("LAN server stopped.")
        self._update_status()

    def use_lan_base_url(self):
        if not self._server:
            self.btn_server.set_active(True)
        if self._server:
            self._set_field("base_url", self._lan_base())
            self.info_dialog(
                "Base URL set to LAN server",
                f"Subscribe in a podcast app on the same Wi-Fi to:\n\n{self._feed_url()}\n\n"
                "This is for local testing only - switch the Base URL back to your public host "
                "before publishing.")

    # --------------------------------------------------------------------------
    # Status, log, dialogs, helpers
    # --------------------------------------------------------------------------
    def _update_status(self):
        n = len(self.tracks)
        total = sum(t.size for t in self.tracks)
        secs = sum(t.duration or 0 for t in self.tracks)
        self.lbl_status_tracks.set_text(
            f"{n} track{'s' if n != 1 else ''}  \u2022  {fmt_duration(secs)}  \u2022  {fmt_size(total)}")
        if self._last_generated:
            self.lbl_status_gen.set_text(f"feed.xml updated {self._last_generated.strftime('%H:%M:%S')}")
        else:
            p = self._feed_path()
            if p and os.path.isfile(p):
                ts = datetime.fromtimestamp(os.path.getmtime(p)).strftime("%b %d %H:%M")
                self.lbl_status_gen.set_text(f"feed.xml last written {ts}")
            else:
                self.lbl_status_gen.set_text("feed.xml not generated")
        ctx = self.lbl_status_server.get_style_context()
        if self._server:
            self.lbl_status_server.set_text(f"\u25cf LAN  {self._lan_base()}/feed.xml")
            ctx.add_class("status-live")
        else:
            self.lbl_status_server.set_text("LAN server off")
            ctx.remove_class("status-live")

    def _flash_status(self, text):
        self.lbl_status_gen.set_text(f"\u2713 {text}")
        GLib.timeout_add_seconds(4, lambda: (self._update_status(), False)[1])

    def log(self, text, tag=None):
        buf = self.log_view.get_buffer()
        end = buf.get_end_iter()
        buf.insert_with_tags_by_name(end, datetime.now().strftime("[%H:%M:%S] "), "time")
        end = buf.get_end_iter()
        if tag:
            buf.insert_with_tags_by_name(end, text + "\n", tag)
        else:
            buf.insert(end, text + "\n")
        self.log_view.scroll_to_mark(buf.get_insert(), 0, False, 0, 0)
        buf.place_cursor(buf.get_end_iter())
        return False

    def _on_switch_page(self, _nb, _page, num):
        if num == 1:
            self._load_xml_preview()

    def copy_feed_url(self):
        url = self._feed_url()
        if url:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(url, -1)
            self._flash_status("Feed URL copied")

    def _xdg_open(self, path):
        if path and os.path.exists(path):
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_uri(), None)

    def info_dialog(self, title, text):
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                              buttons=Gtk.ButtonsType.OK, text=title)
        d.format_secondary_text(text)
        d.run()
        d.destroy()

    def error_dialog(self, title, text):
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.ERROR,
                              buttons=Gtk.ButtonsType.CLOSE, text=title)
        d.format_secondary_text(text)
        d.run()
        d.destroy()

    def on_open_folder(self):
        dlg = Gtk.FileChooserDialog(title="Choose Feed Folder", parent=self,
                                    action=Gtk.FileChooserAction.SELECT_FOLDER)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.OK)
        if self.folder:
            dlg.set_current_folder(self.folder)
        elif os.path.isdir(os.path.expanduser("~/Music")):
            dlg.set_current_folder(os.path.expanduser("~/Music"))
        path = dlg.get_filename() if dlg.run() == Gtk.ResponseType.OK else None
        dlg.destroy()
        if path:
            self.open_folder(path)

    def show_shortcuts(self):
        self.info_dialog("Keyboard Shortcuts", "\n".join([
            "F5 / Ctrl+S        Generate feed.xml",
            "F6                 Generate & Publish",
            "Ctrl+O             Open feed folder",
            "Ctrl+I             Add tracks",
            "Ctrl+R             Rescan folder",
            "Ctrl+B / F9        Toggle settings sidebar",
            "Space              Play / pause selected track",
            "Ctrl+Shift+C       Copy feed URL",
            "Delete             Rename / remove track",
            "Ctrl+1 / 2 / 3     Tracks / feed.xml / Log",
            "Ctrl+Q             Quit",
            "",
            "Tip: drag audio files onto the window to add them.",
        ]))

    def show_about(self):
        about = Gtk.AboutDialog(transient_for=self, modal=True)
        about.set_program_name(self.APP_NAME)
        about.set_version(self.APP_VERSION)
        about.set_comments("Podcast & RSS feed studio for a folder of audio tracks.\n"
                           "A member of the PythonPanel family.")
        about.set_logo_icon_name("rsspanel")
        about.run()
        about.destroy()

    def _setup_shortcuts(self):
        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)

        def bind(key, mods, cb):
            k, m = Gtk.accelerator_parse(key)
            accel.connect(k, m, Gtk.AccelFlags.VISIBLE, lambda *a: (cb(), True)[1])

        bind("F5", 0, self.generate_feed)
        bind("<Control>s", 0, self.generate_feed)
        bind("F6", 0, self.publish)
        bind("<Control>o", 0, self.on_open_folder)
        bind("<Control>i", 0, self.on_add_tracks)
        bind("<Control>r", 0, self.refresh)
        bind("<Control>b", 0, lambda: self.btn_sidebar.set_active(not self.btn_sidebar.get_active()))
        bind("F9", 0, lambda: self.btn_sidebar.set_active(not self.btn_sidebar.get_active()))
        bind("<Control><Shift>c", 0, self.copy_feed_url)
        bind("<Control>q", 0, self.close)
        for i in range(3):
            bind(f"<Control>{i + 1}", 0, lambda i=i: self.notebook.set_current_page(i))

        def on_tree_key(_w, ev):
            if ev.keyval == Gdk.KEY_space:
                self.toggle_play()
                return True
            if ev.keyval == Gdk.KEY_Delete:
                self.on_remove_track()
                return True
            return False

        self.tree.connect("key-press-event", on_tree_key)

    def _setup_drag_and_drop(self):
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_add_uri_targets()

        def on_drop(_w, _ctx, _x, _y, data, _info, _time):
            paths = []
            for uri in data.get_uris():
                p = unquote(urlparse(uri).path)
                if os.path.isdir(p) and not self.tracks:
                    self.open_folder(p)
                    return
                paths.append(p)
            self.import_files(paths)

        self.connect("drag-data-received", on_drop)

    # Session --------------------------------------------------------------
    @staticmethod
    def _session_file():
        d = os.path.expanduser("~/.config/rsspanel")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "session.txt")

    def _load_last_folder(self):
        try:
            with open(self._session_file(), encoding="utf-8") as f:
                p = f.read().strip()
                return p if os.path.isdir(p) else None
        except OSError:
            return None

    def _save_last_folder(self, folder):
        try:
            with open(self._session_file(), "w", encoding="utf-8") as f:
                f.write(folder)
        except OSError:
            pass

    def _on_delete_event(self, *_):
        self.stop_playback()
        if self._server:
            self._stop_server()
        if self._monitor:
            self._monitor.cancel()
        return False


def shutil_copy(src, dst):
    import shutil
    shutil.copy2(src, dst)


def shutil_which(cmd):
    import shutil
    return shutil.which(cmd)


class RSSpanelApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.linuxmint.rsspanel",
                         flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.NON_UNIQUE)
        GLib.set_application_name("RSSpanel")
        GLib.set_prgname("rsspanel")

    def do_activate(self):
        RSSpanelWindow(self).present()

    def do_open(self, files, _n, _hint):
        for f in files:
            p = f.get_path()
            if p and os.path.isfile(p):
                p = os.path.dirname(p)
            RSSpanelWindow(self, initial_folder=p).present()


def main():
    app = RSSpanelApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())

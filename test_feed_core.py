#!/usr/bin/env python3
"""Unit tests for RSSpanel's feed_core module."""

import os
import struct
import tempfile
import unittest
import wave
import xml.dom.minidom
from pathlib import Path

import feed_core


def make_wav(path: Path, seconds=1.0, rate=8000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(rate * seconds))


class FeedCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_wav_with_spaces_and_duration(self):
        make_wav(self.dir / "Blue Grunge.wav", seconds=2)
        tracks = feed_core.scan_folder(self.dir)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].title, "Blue Grunge")
        self.assertAlmostEqual(tracks[0].duration, 2.0, places=2)
        self.assertEqual(tracks[0].mime, "audio/wav")

    def test_newest_first(self):
        make_wav(self.dir / "old.wav")
        make_wav(self.dir / "new.wav")
        os.utime(self.dir / "old.wav", (1000, 1000))
        os.utime(self.dir / "new.wav", (2000, 2000))
        names = [t.name for t in feed_core.scan_folder(self.dir)]
        self.assertEqual(names, ["new.wav", "old.wav"])

    def test_mp3_preferred_over_wav_keeps_original_date(self):
        make_wav(self.dir / "Song.wav")
        (self.dir / "Song.mp3").write_bytes(b"\xff\xfb" + b"\0" * 100)
        os.utime(self.dir / "Song.wav", (1000, 1000))
        os.utime(self.dir / "Song.mp3", (5000, 5000))
        tracks = feed_core.scan_folder(self.dir)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].name, "Song.mp3")
        self.assertEqual(tracks[0].mtime, 1000)
        self.assertEqual([a.name for a in tracks[0].alternates], ["Song.wav"])

    def test_scan_tracks_in_subfolder(self):
        tracks_dir = self.dir / "tracks"
        tracks_dir.mkdir()
        make_wav(tracks_dir / "Subfolder Song.wav", seconds=3)
        tracks = feed_core.scan_folder(self.dir)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].title, "Subfolder Song")
        self.assertEqual(tracks[0].path, tracks_dir / "Subfolder Song.wav")

    def test_ignores_hidden_and_non_audio(self):
        make_wav(self.dir / ".hidden.wav")
        (self.dir / "notes.txt").write_text("x")
        self.assertEqual(feed_core.scan_folder(self.dir), [])

    def test_feed_xml_valid_escaped_and_encoded(self):
        make_wav(self.dir / "Rock & Roll <Live>.wav", seconds=3)
        cfg = feed_core.load_config(self.dir)
        cfg["base_url"] = "https://example.com/blues/"
        cfg["title"] = "Dean's Blues & More"
        cfg["image_url"] = "https://example.com/cover.jpg"
        out = feed_core.write_feed(self.dir, cfg)
        text = out.read_text(encoding="utf-8")
        dom = xml.dom.minidom.parseString(text)  # raises if invalid
        enc = dom.getElementsByTagName("enclosure")[0]
        self.assertEqual(enc.getAttribute("url"),
                         "https://example.com/blues/Rock%20%26%20Roll%20%3CLive%3E.wav")
        self.assertEqual(dom.getElementsByTagName("itunes:duration")[0].firstChild.data, "00:00:03")
        self.assertIn("GMT", dom.getElementsByTagName("pubDate")[0].firstChild.data)

    def test_overrides_and_config_roundtrip(self):
        make_wav(self.dir / "track.wav")
        cfg = feed_core.load_config(self.dir)
        cfg["tracks"] = {"track.wav": {"title": "Custom", "description": "Desc"}}
        feed_core.save_config(self.dir, cfg)
        cfg2 = feed_core.load_config(self.dir)
        t = feed_core.scan_folder(self.dir, cfg2)[0]
        self.assertEqual((t.title, t.description), ("Custom", "Desc"))

    def test_default_title_is_folder_name(self):
        self.assertEqual(feed_core.load_config(self.dir)["title"], self.dir.name)

    def test_formatters(self):
        self.assertEqual(feed_core.fmt_duration(161), "02:41")
        self.assertEqual(feed_core.fmt_duration(3725), "01:02:05")
        self.assertEqual(feed_core.fmt_duration(None), "--:--")
        self.assertEqual(feed_core.fmt_size(31594692), "30.1 MB")

    def test_video_mp4_and_hosted_url_override(self):
        (self.dir / "Blue Grunge.mp4").write_bytes(b"\0" * 512)
        cfg = feed_core.load_config(self.dir)
        cfg["github_repo"] = "example/my-podcast-feed"
        cfg["tracks"] = {
            "Blue Grunge.mp4": {
                "title": "Blue Grunge",
                "url": "https://github.com/example/my-podcast-feed/releases/download/episodes/Blue.Grunge.mp4",
                "pub": 1700000000,
            }
        }
        out = feed_core.write_feed(self.dir, cfg)
        dom = xml.dom.minidom.parseString(out.read_text(encoding="utf-8"))
        enc = dom.getElementsByTagName("enclosure")[0]
        self.assertEqual(enc.getAttribute("type"), "video/mp4")
        self.assertEqual(
            enc.getAttribute("url"),
            "https://github.com/example/my-podcast-feed/releases/download/episodes/Blue.Grunge.mp4",
        )
        self.assertTrue((self.dir / "index.html").is_file())


if __name__ == "__main__":
    unittest.main()

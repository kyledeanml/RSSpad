# Daily Dean Blues Instrumentals — RSSpad Studio

Video podcast feed and **RSSpad** studio (part of the **PythonPad** application suite for Linux Mint Cinnamon).

- **Live RSS Feed:** `https://kyledeanml.github.io/daily-dean-blues-instrumentals/feed.xml`
- **Web Player Landing Page:** `https://kyledeanml.github.io/daily-dean-blues-instrumentals/`

## Daily Workflow with RSSpad

1. Drop any new `.mp4` (or `.mp3`/`.wav`) episode into `/home/bluechile/Videos/Daily Dean Blues Instrumentals`.
2. Open **RSSpad** (or run `rsspad` from your terminal / Cinnamon menu).
3. Click the **Send / Publish** button (`F6`) in the header bar (or run `python3 feed_core.py --sync-github .`).
   - RSSpad uploads any new `.mp4` files to the repository's GitHub Release (`episodes`) so large videos bypass GitHub's 100 MB git file limit.
   - Regenerates `feed.xml` and `index.html` with direct streaming enclosure links and commits/pushes to GitHub Pages.

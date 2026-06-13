# termtok

A TikTok-style vertical video feed, rendered in your terminal.

Videos are decoded with OpenCV and drawn as truecolor half-block (`▀`) pixels.
Scroll with your mouse wheel (or arrow keys) to move between videos — the feed
uses momentum-and-snap physics so a flick carries you forward and eases cleanly
into place, just like the real app. It plays from a local folder, or streams a
live TikTok feed (downloading clips on demand into a bounded cache).

## Setup

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements-player.txt   # player
uv pip install --python .venv/bin/python TikTokApi python-dotenv yt-dlp curl_cffi  # streaming
.venv/bin/python -m playwright install chromium                       # streaming
```

## Run

### Local folder (offline, default)

```bash
./bin/termtok                 # plays everything in ./.videos
./bin/termtok /path/to/clips  # play a different folder
./bin/termtok -n 5            # cap how many videos to load
```

### Stream YouTube Shorts (easiest — no token, no browser)

Needs `yt-dlp` (+ `curl_cffi`) and a **JavaScript runtime** so yt-dlp can solve
YouTube's stream challenge — without it many videos fail as "This video is not
available". Install one of deno/node (`brew install deno`). termtok passes
`--remote-components ejs:github`, so yt-dlp downloads the challenge solver once
(cached) on the first run. No account, API key, or Playwright required.

```bash
./bin/termtok --yt-search cats              # search Shorts
./bin/termtok --yt-channel MrBeast          # a channel's Shorts
./bin/termtok --yt-url https://www.youtube.com/@NASA/shorts
./bin/termtok --yt-search cats --cache-size 200   # cache up to 200 MB (default 50)
```

### Stream from TikTok (needs ms_token + Playwright)

```bash
./bin/termtok --trending              # For-You feed
./bin/termtok --user davidteathercodes
./bin/termtok --tag cats
./bin/termtok --related https://www.tiktok.com/@user/video/123
```

Videos stream in as you scroll: the next few are downloaded ahead of the
playhead into `./.cache` (reused across runs), and an LRU eviction keeps the
cache under `--cache-size` while never deleting videos you're about to watch.
Keep `--cache-size` comfortably above ~5 clips so the protected playhead window
fits.

**How streaming works.** Both backends download mp4s with **yt-dlp**. They
differ only in *discovery*:

- **YouTube** — yt-dlp does discovery too (it enumerates a channel/search/
  playlist with `--flat-playlist`). Nothing else required.
- **TikTok** — TikTokApi (async + Playwright) lists the feed, but TikTok strips
  the playable URL from its API responses, so yt-dlp still does the actual
  download by watch URL. Photo/slideshow posts (audio only, no video) can't be
  played and are skipped with a log note.

So if you just want it working with minimal fuss, prefer the YouTube flags.

**`ms_token` is required for streaming.** TikTokApi is an unofficial scraper, so
you must supply a session token harvested from a logged-in browser
(DevTools → Application → Cookies → `msToken`). Provide it via `--ms-token`,
the `ms_token` environment variable, or an `.env` file (`ms_token=...`). Without
a valid token TikTok returns empty/blocked responses (e.g. status `10201`), and
`termtok` shows that in the status bar rather than crashing. Expect streaming to
break periodically and need a fresh token — that's the nature of scraping.
`main.py` is a standalone example of fetching with TikTokApi.

To run it as just `termtok`, put `bin/` on your `PATH` or symlink it:

```bash
ln -s "$PWD/bin/termtok" /usr/local/bin/termtok
```

### Debugging

The TUI can't print to the screen, so logs go to a file (`./termtok.log` by
default, rotating). Use `--debug` for verbose output:

```bash
./bin/termtok --tag cats --debug
tail -f termtok.log          # watch in another terminal while it runs
```

The log shows session setup, where your `ms_token` came from (or `MISSING`),
each video queued/downloaded/evicted, and TikTok's raw responses — including the
`10201` status that means your token is missing or expired. Change the path with
`--log-file PATH`.

### Controls

| Input                | Action            |
| -------------------- | ----------------- |
| Mouse wheel / ↑ ↓     | Scroll videos     |
| `q` / `Ctrl-C`        | Quit              |

A true-color terminal gives the best results (yours reports `truecolor`).
Larger terminal windows render more detail; smaller windows run faster.

## How it works

| File                  | Responsibility                                                    |
| --------------------- | ----------------------------------------------------------------- |
| `termtok/video.py`    | Decode + loop one video, aspect-fit it to the viewport.           |
| `termtok/physics.py`  | Momentum + critically-damped snap scroll (the TikTok feel).       |
| `termtok/render.py`   | Truecolor half-block renderer with diff-based, flicker-free draws. |
| `termtok/terminal.py` | Raw mode, alt screen, SGR mouse-wheel + key parsing.              |
| `termtok/source.py`   | The `Source` seam: local folder vs. streaming feed.              |
| `termtok/fetcher.py`  | Streaming backends (TikTok / YouTube) + bounded LRU cache.        |
| `termtok/feed.py`     | Runs the loop, composites the scroll transition over a `Source`.  |

Each video is rendered into a buffer that exactly fills the viewport, so a
scroll mid-transition is just a vertical slice of two stacked buffers: the
outgoing video slides up while the incoming one slides in below.

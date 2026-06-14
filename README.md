# termtok

A TikTok-style vertical video feed, rendered in your terminal.

Videos are decoded with OpenCV and drawn as truecolor half-block (`▀`) pixels,
with the focused video's **audio** played via ffplay. Scroll with your mouse
wheel (or arrow keys) to move between videos — the feed uses momentum-and-snap
physics so a flick carries you forward and eases cleanly into place, just like
the real app. It streams YouTube Shorts or a TikTok feed (downloading clips on
demand into a bounded cache), or plays a local folder.

Landing on a video restarts it from the top and plays its sound; scrolling away
or pausing stops it. Audio needs `ffmpeg` (`brew install ffmpeg`); without it the
video still plays, silently.

## Setup

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements-player.txt   # player
uv pip install --python .venv/bin/python TikTokApi python-dotenv yt-dlp curl_cffi  # streaming
.venv/bin/python -m playwright install chromium                       # streaming (TikTok)
brew install ffmpeg                                                   # audio (ffplay)
```

## Run

```bash
./bin/termtok                 # default: stream trending YouTube Shorts (#shorts)
```

### Local folder (offline)

```bash
./bin/termtok /path/to/clips  # play a folder of videos
./bin/termtok ./.videos -n 5  # cap how many videos to load
```

### Streaming

One set of feed flags works for both platforms; pick the platform with
`-p/--platform` (default `youtube`). With no feed flag you get that platform's
default feed (YouTube `#shorts`, or the TikTok For-You feed).

```bash
./bin/termtok                       # default: trending YouTube Shorts
./bin/termtok --search cats         # YouTube Shorts search
./bin/termtok --user MrBeast        # a channel's Shorts
./bin/termtok --tag funny           # a hashtag feed
./bin/termtok --url https://www.youtube.com/@NASA/shorts
./bin/termtok --search cats --cache-size 200   # cache up to 200 MB (default 50)

./bin/termtok -p tiktok                         # TikTok For-You
./bin/termtok -p tiktok --user davidteathercodes
./bin/termtok -p tiktok --tag cats
./bin/termtok -p tiktok --url https://www.tiktok.com/@user/video/123  # related
```

`--search` is YouTube-only (TikTok exposes no public video search).

**YouTube** needs `yt-dlp` (+ `curl_cffi`) and a **JavaScript runtime** so yt-dlp
can solve YouTube's stream challenge — without it many videos fail as "This video
is not available". Install deno or node (`brew install deno`). termtok passes
`--remote-components ejs:github`, so yt-dlp downloads the challenge solver once
(cached) on first run. No account, API key, or Playwright required.

**TikTok** (`-p tiktok`) needs an `ms_token` + Playwright (see below).

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
| `Space`               | Play / pause      |
| `m`                   | Mute / unmute     |
| `q` / `Esc` / `Ctrl-C`| Quit              |

Set the starting volume with `--volume 0-100` (default 70; `0` mutes).

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

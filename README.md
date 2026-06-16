# termtok

```text
    __                      __        __  
   / /____  _________ ___  / /_____  / /__
  / __/ _ \/ ___/ __ `__ \/ __/ __ \/ //_/
 / /_/  __/ /  / / / / / / /_/ /_/ / ,<   
 \__/\___/_/  /_/ /_/ /_/\__/\____/_/|_|  
```

[![Release](https://img.shields.io/github/v/release/flikkr/termtok)](https://github.com/flikkr/termtok/releases/latest) [![Build](https://img.shields.io/github/actions/workflow/status/flikkr/termtok/build.yml?label=build)](https://github.com/flikkr/termtok/actions/workflows/build.yml) [![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey)](#) [![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

A TikTok-style vertical video feed, rendered in your terminal. Just because you can, doesn't mean you should... but I did.

After coming across [this post on Reddit](https://www.reddit.com/r/SideProject/comments/1u2z50q/i_built_an_unblockable_video_stream_it_renders/), I did the thing that seemed like the next obvious evolution in this project. Armed with Claude my side, I prompted my way to a semi-functioning verion of `termtok`. It uses Youtube shorts at the content layer since TikTok has strong anti-scraping measures.

Don't download this expecting anything polished, it's really just an excuse for me to burn through some credits for fun. Credit to the original author of [ASCILINE](https://github.com/YusufB5/ASCILINE) for the cool project!

## Installation

To install `termtok` (macOS/Linux):

```bash
curl -fsSL https://raw.githubusercontent.com/flikkr/termtok/main/install.sh | sh
```

## Local Development Setup

To run from source and modify the code:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt                    # player
uv pip install TikTokApi python-dotenv yt-dlp curl_cffi  # streaming
python -m playwright install chromium                 # streaming (TikTok)
brew install ffmpeg                                   # audio (ffplay)
```

## Run

After activating the venv (`source .venv/bin/activate`), run:

```bash
python -m termtok       # default: stream YouTube Shorts
```

Or if using the installed binary:

```bash
termtok                 # default: stream YouTube Shorts
```

### Streaming

Landing on a video restarts it from the top and plays its sound; scrolling away
or pausing stops it. Audio needs `ffmpeg` (`brew install ffmpeg`); without it the
video still plays, silently.

One set of feed flags works for both platforms; pick the platform with
`-p/--platform` (default `youtube`). With no feed flag you get that platform's
default feed (YouTube `#shorts`, or the TikTok For-You feed).

```bash
termtok                       # default: trending YouTube Shorts
termtok --search cats         # YouTube Shorts search
termtok --user MrBeast        # a channel's Shorts
termtok --tag funny           # a hashtag feed
termtok --url https://www.youtube.com/@NASA/shorts
termtok --search cats --cache-size 200   # cache up to 200 MB (default 50)

termtok -p tiktok                         # TikTok For-You
termtok -p tiktok --user davidteathercodes
termtok -p tiktok --tag cats
termtok -p tiktok --url https://www.tiktok.com/@user/video/123  # related
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
termtok --tag cats --debug
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

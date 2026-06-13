# termtok

A TikTok-style vertical video feed, rendered in your terminal.

Videos in `.videos/` are decoded with OpenCV and drawn as truecolor
half-block (`▀`) pixels. Scroll with your mouse wheel (or arrow keys) to move
between videos — the feed uses momentum-and-snap physics so a flick carries you
forward and eases cleanly into place, just like the real app.

This repo also contains `main.py`, an example TikTok fetcher (downloads videos
into `.videos/`). The player below only cares about the files already there.

## Setup

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements-player.txt
```

## Run

```bash
./bin/termtok                 # plays everything in ./.videos
./bin/termtok /path/to/clips  # play a different folder
./bin/termtok -n 5            # cap how many videos to load
```

To run it as just `termtok`, put `bin/` on your `PATH` or symlink it:

```bash
ln -s "$PWD/bin/termtok" /usr/local/bin/termtok
```

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
| `termtok/feed.py`     | Discovers videos, runs the loop, composites the scroll transition. |

Each video is rendered into a buffer that exactly fills the viewport, so a
scroll mid-transition is just a vertical slice of two stacked buffers: the
outgoing video slides up while the incoming one slides in below.

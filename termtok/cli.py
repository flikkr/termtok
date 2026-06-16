"""termtok CLI entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from . import __version__
from .feed import Feed
from .log import setup_logging
from .source import LocalFolderSource, Source, StreamSource

log = logging.getLogger("termtok.main")

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_CACHE = os.path.join(_PROJECT_DIR, ".cache")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="termtok",
        description="A TikTok-style vertical video feed in your terminal.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="play a local folder of videos instead of streaming",
    )

    parser.add_argument(
        "-p",
        "--platform",
        choices=["youtube", "tiktok"],
        default="youtube",
        help=argparse.SUPPRESS,
    )
    feed = parser.add_mutually_exclusive_group()
    feed.add_argument("--search", metavar="QUERY", help="search for videos (YouTube)")
    feed.add_argument("--user", metavar="NAME", help="a creator's / channel's videos")
    feed.add_argument("--tag", metavar="TAG", help=argparse.SUPPRESS)
    feed.add_argument(
        "--url",
        metavar="URL",
        help="a YouTube channel/playlist URL, or a TikTok video URL (plays related)",
    )

    parser.add_argument(
        "-n", "--count", type=int, default=None, help="local mode: cap how many videos"
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=30.0,
        metavar="FPS",
        help="render frame rate (default: 30)",
    )
    parser.add_argument(
        "--volume",
        type=int,
        default=70,
        metavar="0-100",
        help="audio volume (0 mutes; needs ffplay). default: 70",
    )
    parser.add_argument(
        "--cache-size",
        type=float,
        default=50.0,
        metavar="MB",
        help="max size of the download cache in MB (default: 50)",
    )
    parser.add_argument(
        "--cache-dir", default=_DEFAULT_CACHE, help="where to cache downloads"
    )
    parser.add_argument(
        "--ms-token",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--debug", action="store_true", help="verbose logging to the log file"
    )
    parser.add_argument(
        "--log-file", default=None, help="where to write logs (default: ./termtok.log)"
    )
    args = parser.parse_args(argv)

    log_path = setup_logging(debug=args.debug, path=args.log_file)
    log.info("argv=%s", _redact(argv if argv is not None else sys.argv[1:]))

    if not sys.stdout.isatty():
        print("termtok must run in an interactive terminal.", file=sys.stderr)
        return 1

    try:
        source = _build_source(args)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"termtok: {e}", file=sys.stderr)
        return 1

    Feed(source, volume=args.volume, fps=args.fps).run()
    return 0


def _build_source(args) -> Source:
    cache_bytes = int(max(1.0, args.cache_size) * 1024 * 1024)

    # An explicit local folder bypasses streaming entirely.
    if args.folder is not None:
        return _local_source(args)

    feed = _selected_feed(args)  # (kind, value) or None
    if args.platform == "tiktok":
        return _tiktok_source(args, feed, cache_bytes)
    return _youtube_source(args, feed, cache_bytes)


def _selected_feed(args) -> tuple[str, str] | None:
    if args.search is not None:
        return "search", args.search
    if args.user is not None:
        return "user", args.user
    if args.tag is not None:
        return "tag", args.tag
    if args.url is not None:
        return "url", args.url
    return None


def _redact(argv: list[str]) -> list[str]:
    """Mask the ms_token value so it never lands in the log file."""
    out = list(argv)
    for i, a in enumerate(out):
        if a == "--ms-token" and i + 1 < len(out):
            out[i + 1] = "***"
        elif a.startswith("--ms-token="):
            out[i] = "--ms-token=***"
    return out


def _local_source(args) -> Source:
    source = LocalFolderSource(args.folder, limit=args.count)
    log.info("local mode: folder=%s found=%d videos", args.folder, source.count())
    if source.count() == 0:
        print(
            f"No videos found in {args.folder!r}.\n"
            "Pass a folder of videos, or stream a feed, e.g.:\n"
            "  termtok                     (trending YouTube Shorts)\n"
            "  termtok --search cats       (YouTube Shorts search)\n"
            "  termtok --user mkbhd        (a channel's Shorts)",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return source


def _youtube_source(args, feed: tuple[str, str] | None, cache_bytes: int) -> Source:
    from .fetcher import (
        YouTubeFetcher,
        channel_shorts_url,
        hashtag_url,
        search_url,
    )

    if feed is None:
        url = search_url("cats")
    else:
        kind, val = feed
        url = {
            "search": search_url,
            "user": channel_shorts_url,
            "tag": hashtag_url,
            "url": lambda v: v,
        }[kind](val)
    log.info(
        "youtube source url=%s cache=%sMB dir=%s", url, args.cache_size, args.cache_dir
    )
    return StreamSource(YouTubeFetcher(url, args.cache_dir, cache_bytes))


def _tiktok_source(args, feed: tuple[str, str] | None, cache_bytes: int) -> Source:
    from .fetcher import TikTokFetcher

    if feed is None:
        mode, arg = "trending", None
    else:
        kind, val = feed
        if kind == "search":
            raise ValueError(
                "TikTok video search isn't available — use --tag, --user, or --url"
            )
        mode, arg = {
            "user": ("user", val),
            "tag": ("tag", val.lstrip("#")),
            "url": ("related", val),
        }[kind]

    ms_token, origin = _resolve_ms_token(args.ms_token)
    log.info(
        "tiktok mode=%s arg=%r ms_token=%s cache=%sMB dir=%s",
        mode,
        arg,
        f"{origin}(len={len(ms_token)})" if ms_token else "MISSING",
        args.cache_size,
        args.cache_dir,
    )
    if not ms_token:
        print(
            "warning: no ms_token (set --ms-token, $ms_token, or .env). "
            "TikTok requests will likely fail; harvest one from a logged-in "
            "browser session, or drop -p tiktok to use YouTube Shorts (no token).",
            file=sys.stderr,
        )
    return StreamSource(TikTokFetcher(mode, arg, args.cache_dir, cache_bytes, ms_token))


def _resolve_ms_token(cli_value: str | None) -> tuple[str | None, str]:
    """Return (token, origin) where origin says where it came from."""
    if cli_value:
        return cli_value, "--ms-token"
    token = os.environ.get("ms_token")
    if token:
        return token, "$ms_token"
    try:
        from dotenv import dotenv_values

        token = dotenv_values(os.path.join(_PROJECT_DIR, ".env")).get("ms_token")
        if token:
            return token, ".env"
    except Exception:  # noqa: BLE001
        log.debug("dotenv lookup failed", exc_info=True)
    return None, "none"


if __name__ == "__main__":
    raise SystemExit(main())

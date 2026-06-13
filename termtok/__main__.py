"""termtok CLI entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from .feed import Feed
from .log import setup_logging
from .source import LocalFolderSource, Source, StreamSource

log = logging.getLogger("termtok.main")

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DIR = os.path.join(_PROJECT_DIR, ".videos")
_DEFAULT_CACHE = os.path.join(_PROJECT_DIR, ".cache")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="termtok",
        description="A TikTok-style vertical video feed in your terminal.",
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=_DEFAULT_DIR,
        help="folder of local videos to play (default: ./.videos)",
    )

    feed = parser.add_mutually_exclusive_group()
    # TikTok (needs ms_token + Playwright)
    feed.add_argument("--trending", action="store_true", help="TikTok For-You feed")
    feed.add_argument("--user", metavar="USERNAME", help="TikTok: a creator's videos")
    feed.add_argument("--tag", metavar="HASHTAG", help="TikTok: a hashtag's videos")
    feed.add_argument("--related", metavar="URL", help="TikTok: videos related to URL")
    # YouTube Shorts (just needs yt-dlp — no token, no browser)
    feed.add_argument("--yt-search", metavar="QUERY", help="YouTube Shorts search")
    feed.add_argument("--yt-channel", metavar="NAME", help="a channel's YouTube Shorts")
    feed.add_argument("--yt-url", metavar="URL", help="any YouTube channel/playlist URL")

    parser.add_argument(
        "-n", "--count", type=int, default=None, help="local mode: cap how many videos"
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
        help="TikTok ms_token (else $ms_token, else .env)",
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

    print(f"termtok: logging to {log_path}", file=sys.stderr)
    try:
        source = _build_source(args)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"termtok: {e}", file=sys.stderr)
        return 1

    Feed(source).run()
    return 0


def _build_source(args) -> Source:
    cache_bytes = int(max(1.0, args.cache_size) * 1024 * 1024)

    if args.yt_search or args.yt_channel or args.yt_url:
        return _youtube_source(args, cache_bytes)
    mode, arg = _tiktok_mode(args)
    if mode is not None:
        return _tiktok_source(args, mode, arg, cache_bytes)
    return _local_source(args)


def _redact(argv: list[str]) -> list[str]:
    """Mask the ms_token value so it never lands in the log file."""
    out = list(argv)
    for i, a in enumerate(out):
        if a == "--ms-token" and i + 1 < len(out):
            out[i + 1] = "***"
        elif a.startswith("--ms-token="):
            out[i] = "--ms-token=***"
    return out


def _tiktok_mode(args) -> tuple[str | None, str | None]:
    if args.trending:
        return "trending", None
    if args.user:
        return "user", args.user
    if args.tag:
        return "tag", args.tag.lstrip("#")
    if args.related:
        return "related", args.related
    return None, None


def _local_source(args) -> Source:
    source = LocalFolderSource(args.folder, limit=args.count)
    log.info("local mode: folder=%s found=%d videos", args.folder, source.count())
    if source.count() == 0:
        print(
            f"No videos found in {args.folder!r}.\n"
            "Pass a folder, or stream a feed, e.g.:\n"
            "  termtok --yt-search 'cats'        (YouTube Shorts, no setup)\n"
            "  termtok --user <name>             (TikTok, needs ms_token)",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return source


def _youtube_source(args, cache_bytes: int) -> Source:
    from .fetcher import YouTubeFetcher, channel_shorts_url, search_url

    if args.yt_channel:
        url = channel_shorts_url(args.yt_channel)
    elif args.yt_search:
        url = search_url(args.yt_search)
    else:
        url = args.yt_url
    log.info("youtube source url=%s cache=%sMB dir=%s", url, args.cache_size, args.cache_dir)
    return StreamSource(YouTubeFetcher(url, args.cache_dir, cache_bytes))


def _tiktok_source(args, mode: str, arg: str | None, cache_bytes: int) -> Source:
    from .fetcher import TikTokFetcher

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
            "browser session, or use --yt-search for YouTube Shorts (no token).",
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

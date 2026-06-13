"""termtok CLI entry point."""

from __future__ import annotations

import argparse
import os
import sys

from .feed import Feed, discover_videos

_DEFAULT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".videos"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="termtok",
        description="A TikTok-style vertical video feed in your terminal.",
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=_DEFAULT_DIR,
        help="folder of videos to play (default: ./.videos)",
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=None,
        help="play at most this many videos",
    )
    args = parser.parse_args(argv)

    if not sys.stdout.isatty():
        print("termtok must run in an interactive terminal.", file=sys.stderr)
        return 1

    paths = discover_videos(args.folder)
    if args.count is not None:
        paths = paths[: max(0, args.count)]
    if not paths:
        print(f"No videos found in {args.folder!r}.", file=sys.stderr)
        return 1

    Feed(paths).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

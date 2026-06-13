"""File-based logging.

termtok runs in a full-screen alternate-screen TUI, so anything written to
stdout/stderr during a session corrupts the display. All logging therefore goes
to a rotating file (``termtok.log`` by default). This module also detaches
noisy third-party console handlers (notably TikTokApi's, which logs straight to
stderr) and routes them into the same file so their messages — like TikTok's
``10201`` rejection — are captured for debugging instead of mangling the screen.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LOG_PATH = os.path.join(_PROJECT_DIR, "termtok.log")

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(debug: bool = False, path: str | None = None) -> str:
    """Configure root logging to a rotating file. Returns the log path."""
    path = path or DEFAULT_LOG_PATH
    level = logging.DEBUG if debug else logging.INFO

    root = logging.getLogger()
    root.setLevel(level)
    # Drop any pre-existing handlers (e.g. console) so nothing hits the screen.
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = RotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)

    logging.getLogger("termtok").setLevel(level)
    if not debug:
        # These are chatty; keep them out of the file unless debugging.
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        logging.getLogger("websockets").setLevel(logging.WARNING)

    logging.getLogger("termtok").info("logging started (debug=%s) -> %s", debug, path)
    return path


def attach_library_logger(logger: logging.Logger) -> None:
    """Reroute a third-party logger (e.g. TikTokApi's) into our file.

    Removes its own handlers (which write to the console) and lets it propagate
    to the root file handler instead.
    """
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.propagate = True

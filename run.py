"""PyInstaller entry point.

Runs termtok with proper package context so the package's relative imports
resolve. PyInstaller can't use ``termtok/__main__.py`` directly as the entry
script: it executes that file as the top-level ``__main__`` module with no
parent package, which breaks ``from .feed import Feed`` and friends.
"""

import sys

from termtok.__main__ import main

if __name__ == "__main__":
    sys.exit(main())

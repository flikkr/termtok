"""PyInstaller entry point — imports from termtok.cli to avoid the PyInstaller
bug where importing termtok/__main__.py strips __package__, breaking relative imports."""

import sys

from termtok.cli import main

if __name__ == "__main__":
    sys.exit(main())

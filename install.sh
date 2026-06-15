#!/bin/sh
set -e

REPO="flikkr/termtok"
# Per-user bin dir — no sudo needed.
BIN_DIR="$HOME/.local/bin"
# Helper binaries (yt-dlp, optionally a JS runtime / ffmpeg) live here. termtok
# prepends this dir to PATH for its subprocesses — see termtok/tools.py.
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/termtok/bin"

# Ask a y/n question. Reads from the terminal (stdin is the curl pipe under
# `curl | sh`). No tty → default yes, so automated installs still work.
ask() {
  [ -e /dev/tty ] || return 0   # no terminal: default yes
  printf "%s [Y/n] " "$1" > /dev/tty
  read ans < /dev/tty || return 0
  case "$ans" in [Nn]*) return 1 ;; *) return 0 ;; esac
}

# Detect OS and arch
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux)
    case "$ARCH" in
      x86_64) ARTIFACT="termtok-linux-x86_64"; YTDLP_ASSET="yt-dlp_linux" ;;
      *)
        echo "termtok: unsupported architecture: $ARCH" >&2
        exit 1
        ;;
    esac
    ;;
  Darwin)
    # yt-dlp ships one universal2 macOS binary for both arm64 and x86_64.
    YTDLP_ASSET="yt-dlp_macos"
    case "$ARCH" in
      arm64)  ARTIFACT="termtok-macos-arm64" ;;
      x86_64) ARTIFACT="termtok-macos-x86_64" ;;
      *)
        echo "termtok: unsupported architecture: $ARCH" >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "termtok: unsupported OS: $OS" >&2
    exit 1
    ;;
esac

# Resolve latest release download URL
echo "termtok: fetching latest release info..."
URL="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
  | grep "browser_download_url" \
  | grep "$ARTIFACT" \
  | sed 's/.*"browser_download_url": *"\([^"]*\)".*/\1/')"

if [ -z "$URL" ]; then
  echo "termtok: could not find a release binary for $ARTIFACT" >&2
  echo "  check https://github.com/$REPO/releases for available builds" >&2
  exit 1
fi

# Download termtok itself
TMP="$(mktemp)"
echo "termtok: downloading $ARTIFACT..."
curl -fsSL "$URL" -o "$TMP"
chmod +x "$TMP"

# Install
mkdir -p "$BIN_DIR"
mv "$TMP" "$BIN_DIR/termtok"
echo "termtok: installed to $BIN_DIR/termtok"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "termtok: NOTE — $BIN_DIR is not on your PATH. Add it:"
     echo "    echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc  # or ~/.bashrc" ;;
esac

# yt-dlp — required for streaming. We fetch the official standalone binary so the
# release build (which has no Python environment) can stream out of the box.
if ask "termtok: download yt-dlp? (needed for YouTube/TikTok streaming)"; then
  echo "termtok: downloading yt-dlp..."
  mkdir -p "$DATA_DIR"
  YTDLP_URL="https://github.com/yt-dlp/yt-dlp/releases/latest/download/$YTDLP_ASSET"
  if curl -fsSL "$YTDLP_URL" -o "$DATA_DIR/yt-dlp"; then
    chmod +x "$DATA_DIR/yt-dlp"
    echo "termtok: yt-dlp installed to $DATA_DIR/yt-dlp"
  else
    rm -f "$DATA_DIR/yt-dlp"
    echo "termtok: WARNING — could not download yt-dlp; streaming will not work." >&2
    echo "  install it manually: https://github.com/yt-dlp/yt-dlp#installation" >&2
  fi
else
  echo "termtok: skipped yt-dlp. Streaming won't work until you install it:"
  echo "  https://github.com/yt-dlp/yt-dlp#installation  (drop it in $DATA_DIR)"
fi

echo ""
echo "termtok: installed."
echo ""
echo "  Run:  termtok"
echo "  Docs: https://github.com/$REPO"
echo ""
echo "Optional, for the full experience:"
echo "  • YouTube needs a JavaScript runtime (node or deno) to decode most Shorts."
echo "      macOS:  brew install node        Linux: see https://nodejs.org/en/download"
echo "    (already have node? nothing to do.)"
echo "  • Audio needs ffmpeg (provides ffplay)."
echo "      macOS:  brew install ffmpeg      Linux: apt install ffmpeg  (or your pkg mgr)"
echo ""
echo "Tip: drop a 'node'/'deno'/'ffplay' binary into $DATA_DIR"
echo "     and termtok will find it without touching your PATH."

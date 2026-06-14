#!/bin/sh
set -e

REPO="kazymirrabier/termtok"
BIN_DIR="/usr/local/bin"

# Detect OS and arch
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux)
    case "$ARCH" in
      x86_64) ARTIFACT="termtok-linux-x86_64" ;;
      *)
        echo "termtok: unsupported architecture: $ARCH" >&2
        exit 1
        ;;
    esac
    ;;
  Darwin)
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

# Download
TMP="$(mktemp)"
echo "termtok: downloading $ARTIFACT..."
curl -fsSL "$URL" -o "$TMP"
chmod +x "$TMP"

# Install
if [ -w "$BIN_DIR" ]; then
  mv "$TMP" "$BIN_DIR/termtok"
else
  echo "termtok: installing to $BIN_DIR (may prompt for password)"
  sudo mv "$TMP" "$BIN_DIR/termtok"
fi

echo "termtok: installed to $BIN_DIR/termtok"
echo ""
echo "  Run:  termtok"
echo "  Docs: https://github.com/$REPO"
echo ""
echo "Note: streaming needs yt-dlp + deno. Audio needs ffmpeg."
echo "  brew install ffmpeg deno && pip install yt-dlp"

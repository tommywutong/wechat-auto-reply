#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$REPO_DIR/.build"
mkdir -p "$BUILD_DIR"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "此脚本只能在 macOS 上运行。" >&2
  exit 1
fi

swiftc -O -framework Vision -framework Foundation -framework ImageIO \
  "$REPO_DIR/macos/vision_ocr.swift" -o "$BUILD_DIR/vision-ocr"
swiftc -O -framework CoreGraphics -framework Foundation \
  "$REPO_DIR/macos/mouse_click.swift" -o "$BUILD_DIR/mouse-click"
swiftc -O -framework CoreGraphics -framework Foundation \
  "$REPO_DIR/macos/mouse_scroll.swift" -o "$BUILD_DIR/mouse-scroll"
chmod +x "$BUILD_DIR/vision-ocr" "$BUILD_DIR/mouse-click" "$BUILD_DIR/mouse-scroll"
echo "macOS OCR 和鼠标辅助程序已编译到 $BUILD_DIR"

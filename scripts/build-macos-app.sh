#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_PROJECT="$REPO_DIR/macos/TraceMemoAutoReplyApp"
DIST_DIR="$REPO_DIR/dist"
APP_BUNDLE="$DIST_DIR/TraceMemo 自动回复.app"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "此脚本只能在 macOS 上运行。" >&2
  exit 1
fi

swift build --package-path "$APP_PROJECT" --configuration release

PRODUCT_DIR="$APP_PROJECT/.build/arm64-apple-macosx/release"
if [[ ! -x "$PRODUCT_DIR/TraceMemoAutoReply" ]]; then
  PRODUCT_DIR="$APP_PROJECT/.build/release"
fi
if [[ ! -x "$PRODUCT_DIR/TraceMemoAutoReply" ]]; then
  echo "找不到 Swift 构建产物。" >&2
  exit 1
fi

mkdir -p "$DIST_DIR"
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"
cp "$PRODUCT_DIR/TraceMemoAutoReply" "$APP_BUNDLE/Contents/MacOS/TraceMemoAutoReply"
cp "$APP_PROJECT/Resources/Info.plist" "$APP_BUNDLE/Contents/Info.plist"
chmod +x "$APP_BUNDLE/Contents/MacOS/TraceMemoAutoReply"

echo "App 已生成：$APP_BUNDLE"
echo "首次打开后，在 App 底部选择项目目录：$REPO_DIR"

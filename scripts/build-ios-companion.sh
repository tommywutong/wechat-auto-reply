#!/usr/bin/env bash
# 构建 iPhone 控制端。默认不修改用户的 Xcode 设置，产物写入 dist/。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$REPO_DIR/ios/companion"
PROJECT="$PROJECT_DIR/TraceMemoRemote.xcodeproj"
SCHEME="TraceMemoRemote"
BUILD_DIR="${WXAUTO_IOS_BUILD_DIR:-$REPO_DIR/.build/ios-companion}"
DIST_DIR="${WXAUTO_IOS_DIST_DIR:-$REPO_DIR/dist}"
CONFIGURATION="${WXAUTO_IOS_CONFIGURATION:-Release}"
TEAM_ID="${DEVELOPMENT_TEAM:-${WXAUTO_IOS_TEAM_ID:-}}"

mkdir -p "$BUILD_DIR" "$DIST_DIR"
rm -rf "$BUILD_DIR/archive" "$BUILD_DIR/export" "$BUILD_DIR/simulator" \
  "$DIST_DIR/TraceMemoRemote.ipa" "$DIST_DIR/TraceMemoRemote-unsigned.xcarchive" \
  "$DIST_DIR/TraceMemoRemote.xcarchive" "$DIST_DIR/TraceMemoRemote-simulator.app"

COMMON=(
  -project "$PROJECT"
  -scheme "$SCHEME"
  -configuration "$CONFIGURATION"
  -derivedDataPath "$BUILD_DIR/derived"
)

echo "构建 iOS 模拟器包..."
xcodebuild "${COMMON[@]}" -sdk iphonesimulator \
  CODE_SIGNING_ALLOWED=NO build >/dev/null
SIMULATOR_APP="$BUILD_DIR/derived/Build/Products/${CONFIGURATION}-iphonesimulator/TraceMemoRemote.app"
if [[ -d "$SIMULATOR_APP" ]]; then
  cp -R "$SIMULATOR_APP" "$DIST_DIR/TraceMemoRemote-simulator.app"
fi

ARCHIVE_PATH="$BUILD_DIR/archive/TraceMemoRemote.xcarchive"
UNSIGNED_ARCHIVE_PATH="$BUILD_DIR/archive/TraceMemoRemote-unsigned.xcarchive"
ARCHIVE_ARGS=("${COMMON[@]}" -sdk iphoneos -archivePath "$ARCHIVE_PATH")
if [[ -n "$TEAM_ID" ]]; then
  ARCHIVE_ARGS+=(DEVELOPMENT_TEAM="$TEAM_ID" CODE_SIGN_STYLE=Automatic)
fi

ARCHIVE_COPIED=0
echo "尝试归档真机包..."
if xcodebuild "${ARCHIVE_ARGS[@]}" archive -allowProvisioningUpdates >"$BUILD_DIR/archive.log" 2>&1; then
  ARCHIVE_APP="$ARCHIVE_PATH/Products/Applications/TraceMemoRemote.app"
  if [[ -d "$ARCHIVE_APP" ]]; then
    cp -R "$ARCHIVE_PATH" "$DIST_DIR/TraceMemoRemote.xcarchive"
    ARCHIVE_COPIED=1
    cat >"$BUILD_DIR/export-options.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>development</string>
  <key>signingStyle</key><string>automatic</string>
</dict></plist>
PLIST
    if xcodebuild -exportArchive \
      -archivePath "$BUILD_DIR/archive/TraceMemoRemote.xcarchive" \
      -exportPath "$BUILD_DIR/export" \
      -exportOptionsPlist "$BUILD_DIR/export-options.plist" \
      -allowProvisioningUpdates >"$BUILD_DIR/export.log" 2>&1; then
      IPA="$BUILD_DIR/export/TraceMemoRemote.ipa"
      if [[ -f "$IPA" ]]; then
        cp "$IPA" "$DIST_DIR/TraceMemoRemote.ipa"
        echo "已生成可安装 IPA：$DIST_DIR/TraceMemoRemote.ipa"
      else
        echo "真机归档成功，但导出没有生成 IPA。详细原因：$BUILD_DIR/export.log"
      fi
    else
      echo "真机归档成功，但 IPA 导出失败。详细原因：$BUILD_DIR/export.log"
    fi
  else
    echo "归档命令报告成功，但未找到应用归档目录。详细原因：$BUILD_DIR/archive.log"
  fi
else
  echo "签名归档失败，生成可重新签名的未签名归档..."
  if xcodebuild "${COMMON[@]}" -sdk iphoneos -archivePath "$UNSIGNED_ARCHIVE_PATH" \
    CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO archive >"$BUILD_DIR/unsigned-archive.log" 2>&1; then
    cp -R "$UNSIGNED_ARCHIVE_PATH" "$DIST_DIR/TraceMemoRemote-unsigned.xcarchive"
    echo "真机归档失败，已保留未签名归档：$DIST_DIR/TraceMemoRemote-unsigned.xcarchive"
  else
    echo "未生成真机归档。签名原因：$BUILD_DIR/archive.log"
    echo "未签名归档原因：$BUILD_DIR/unsigned-archive.log"
  fi
fi

if [[ -d "$DIST_DIR/TraceMemoRemote.ipa" ]]; then
  echo "错误：IPA 应为文件而不是目录。" >&2
  exit 1
fi
if [[ -f "$DIST_DIR/TraceMemoRemote.ipa" ]]; then
  shasum -a 256 "$DIST_DIR/TraceMemoRemote.ipa"
elif [[ "$ARCHIVE_COPIED" -eq 1 ]]; then
  echo "已生成真机归档，但未生成可安装 IPA；请检查 Apple 账号和 provisioning profile。"
else
  echo "未生成可安装 IPA；真机安装需要 Apple Team 与 provisioning profile。"
fi
echo "产物目录：$DIST_DIR"

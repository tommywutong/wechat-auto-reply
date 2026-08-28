#!/usr/bin/env bash
# 确保本机有可用的 TraceMemo Reader。优先使用已运行/已安装版本，
# 否则把固定版本下载到用户目录并以托盘模式启动，不要求用户手动安装 TraceMemo。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_DIR="${TRACEMEMO_RUNTIME_BASE_DIR:-$HOME/Library/Application Support/TraceMemoAutoReply}"
RUNTIME_DIR="$BASE_DIR/runtime"
RUNTIME_APP="$RUNTIME_DIR/TraceMemo.app"
RUNTIME_DATA="$BASE_DIR/data"
DOWNLOAD_DIR="$BASE_DIR/downloads"
LOG_PATH="$BASE_DIR/runtime.log"

VERSION="${TRACEMEMO_RUNTIME_VERSION:-2.2.2}"
ASSET="tracememo-${VERSION}-arm64.dmg"
DOWNLOAD_URL="https://github.com/Wxw-Gu/TraceMemo/releases/download/v${VERSION}/${ASSET}"
EXPECTED_SHA256="09b8a685f5d1d00c6a25e298cae67d72f60f5d76fdf9401f0774226716c84ea0"
HEALTH_URL="http://127.0.0.1:6131/api/v1/health"
AUTH_URL="http://127.0.0.1:6131/api/v1/recent_chat?limit=1"

data_dir_candidates() {
  if [[ -n "${TRACEMEMO_DATA_DIR:-}" ]]; then
    printf '%s\n' "$TRACEMEMO_DATA_DIR"
    return
  fi
  printf '%s\n' \
    "$HOME/Library/Application Support/TraceMemo" \
    "$HOME/Library/Application Support/WechatExplorer" \
    "$RUNTIME_DATA"
}

find_data_dir() {
  local candidate
  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] || continue
    if [[ -f "$candidate/local-api-token.bin" || -f "$candidate/settings.json" || -d "$candidate/database-keys" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done < <(data_dir_candidates)
  printf '%s\n' "$RUNTIME_DATA"
}

find_token_file() {
  local candidate
  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] || continue
    if [[ -f "$candidate/local-api-token.bin" ]]; then
      printf '%s\n' "$candidate/local-api-token.bin"
      return 0
    fi
  done < <(data_dir_candidates)
  return 1
}

health_ready() {
  /usr/bin/curl --connect-timeout 2 --max-time 4 --silent --show-error "$HEALTH_URL" 2>/dev/null \
    | /usr/bin/grep -Eq '"ready"[[:space:]]*:[[:space:]]*true'
}

auth_ready() {
  local token account status
  account="$(/usr/bin/id -un)"
  token="$(/usr/bin/security find-generic-password -a "$account" -s com.wxauto.tracememo-api-token -w 2>/dev/null || true)"
  [[ -n "$token" ]] || return 1
  status="$(/usr/bin/curl --connect-timeout 2 --max-time 8 --silent --show-error \
    -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $token" "$AUTH_URL" 2>/dev/null || true)"
  [[ "$status" == "200" ]]
}

if health_ready; then
  if auth_ready; then exit 0; fi
  echo "TraceMemo Reader 已运行，但 Keychain Token 未通过鉴权。" >&2
  echo "请在 TraceMemo → API Center 复制最新 Token，并更新 macOS Keychain 项 com.wxauto.tracememo-api-token。" >&2
  exit 1
fi

find_app() {
  local candidate
  for candidate in "${TRACEMEMO_APP_PATH:-}" "$REPO_DIR/vendor/TraceMemo.app" \
    "$REPO_DIR/dist/TraceMemo.app" "/Applications/TraceMemo.app" "$RUNTIME_APP"; do
    if [[ -x "$candidate/Contents/MacOS/Electron" && -f "$candidate/Contents/Resources/app.asar" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

app_path="$(find_app || true)"
if [[ -z "$app_path" ]]; then
  mkdir -p "$DOWNLOAD_DIR" "$RUNTIME_DIR"
  archive="$DOWNLOAD_DIR/$ASSET"
  if [[ ! -f "$archive" ]]; then
    /usr/bin/curl --fail --location --retry 3 --connect-timeout 10 --max-time 900 \
      --output "$archive.partial" "$DOWNLOAD_URL"
    actual_sha256="$(/usr/bin/shasum -a 256 "$archive.partial" | /usr/bin/awk '{print $1}')"
    if [[ "$actual_sha256" != "$EXPECTED_SHA256" ]]; then
      /bin/rm -f "$archive.partial"
      echo "TraceMemo 下载校验失败，请重试。" >&2
      exit 1
    fi
    /bin/mv "$archive.partial" "$archive"
  fi
  actual_sha256="$(/usr/bin/shasum -a 256 "$archive" | /usr/bin/awk '{print $1}')"
  [[ "$actual_sha256" == "$EXPECTED_SHA256" ]] || { echo "TraceMemo 缓存校验失败。" >&2; exit 1; }
  mount_dir="$(/usr/bin/mktemp -d "$BASE_DIR/mount.XXXXXX")"
  cleanup() { /usr/bin/hdiutil detach "$mount_dir" >/dev/null 2>&1 || true; /bin/rm -rf "$mount_dir"; }
  trap cleanup EXIT
  /usr/bin/hdiutil attach -nobrowse -readonly -mountpoint "$mount_dir" "$archive" >/dev/null
  /bin/rm -rf "$RUNTIME_APP.installing"
  /bin/cp -R "$mount_dir/TraceMemo.app" "$RUNTIME_APP.installing"
  /bin/mv "$RUNTIME_APP.installing" "$RUNTIME_APP"
  app_path="$RUNTIME_APP"
fi

electron="$app_path/Contents/MacOS/Electron"
if [[ "$app_path" == "$RUNTIME_APP" ]]; then
  data_dir="$(find_data_dir)"
  mkdir -p "$data_dir"
  if [[ ! -f "$data_dir/local-api-token.bin" ]]; then
    token_source="$(find_token_file || true)"
    if [[ -n "$token_source" && "$token_source" != "$data_dir/local-api-token.bin" ]]; then
      /bin/cp "$token_source" "$data_dir/local-api-token.bin"
      /bin/chmod 600 "$data_dir/local-api-token.bin"
    fi
  fi
  if [[ ! -f "$data_dir/local-api-token.bin" ]]; then
    echo "TraceMemo 数据目录缺少加密 API Token：$data_dir" >&2
    echo "请先在 TraceMemo 的 API Center 生成一次 Token，并将同一个 Token 保存到 macOS Keychain。" >&2
    exit 1
  fi
  WXE_USER_DATA="$data_dir" "$electron" "$app_path/Contents/Resources/app.asar" --tray \
    >>"$LOG_PATH" 2>&1 &
else
  /usr/bin/open -gj -a "$app_path" --args --tray >/dev/null 2>&1 || true
fi

for _ in $(/usr/bin/seq 1 30); do
  if health_ready; then
    if auth_ready; then exit 0; fi
    echo "TraceMemo Reader 已启动，但 Keychain Token 与本地 API 不匹配。" >&2
    echo "请在 TraceMemo → API Center 复制最新 Token，并更新 macOS Keychain 项 com.wxauto.tracememo-api-token。" >&2
    exit 1
  fi
  /bin/sleep 1
done
echo "TraceMemo Reader 未在 30 秒内就绪，请检查：$LOG_PATH" >&2
exit 1

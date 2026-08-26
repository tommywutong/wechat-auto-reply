#!/data/data/com.termux/files/usr/bin/bash
#
# 在安卓手机上直接跑规则服务（Termux），不需要任何电脑。
#
# 适合谁：只有安卓、没有常开电脑的人。服务和 App 都在同一台手机上，
# 走 127.0.0.1 回环，不经过局域网，也就没有「手机连不上电脑」这类问题。
#
# 用法：
#   1. 从 F-Droid 装 Termux（Google Play 版本已停止维护，会缺包）
#   2. 把本仓库拷到手机上，cd 进去
#   3. bash scripts/termux-setup.sh
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "==> 安装依赖"
pkg update -y
pkg install -y python

# 注意用 uvicorn 而不是 uvicorn[standard]：后者依赖 uvloop / httptools，
# 需要在手机上编译 C 扩展，很容易失败，而且这点性能这里根本用不上。
pip install --upgrade pip
pip install fastapi uvicorn pyyaml

echo
echo "==> 生成配置"
if [ ! -f core/config.yaml ]; then
    cp core/config.example.yaml core/config.yaml
    echo "已生成 core/config.yaml，等下记得改成你自己的规则"
else
    echo "core/config.yaml 已存在，跳过"
fi

TOKEN_FILE="$REPO_DIR/.wxauto_token"
if [ ! -f "$TOKEN_FILE" ]; then
    # Termux 上不一定有 openssl，用 python 生成
    python -c "import secrets; print(secrets.token_hex(16))" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
fi
TOKEN="$(cat "$TOKEN_FILE")"

echo
echo "==> 写启动脚本"
cat > "$REPO_DIR/run-server.sh" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
set -e
cd "$REPO_DIR"

# 防止系统休眠把服务杀掉。退出时记得 termux-wake-unlock。
termux-wake-lock 2>/dev/null || true

export WXAUTO_CONFIG=core/config.yaml
export WXAUTO_STATE=var/state.json
export WXAUTO_TOKEN="$TOKEN"

# 只监听回环地址：App 和服务在同一台手机上，没必要暴露到局域网。
# 少开一个口，就少一份别人驱动你微信的风险。
exec python -m uvicorn server.app:app --host 127.0.0.1 --port 8848
EOF
chmod +x "$REPO_DIR/run-server.sh"

echo
echo "============================================================"
echo "装好了。"
echo
echo "启动服务："
echo "    ./run-server.sh"
echo
echo "然后在「微信自动回复」App 里填："
echo "    服务地址：http://127.0.0.1:8848"
echo "    token   ：$TOKEN"
echo "    微信号标识：留空即可（只跑一端）"
echo
echo "开机自启（可选）：从 F-Droid 装 Termux:Boot，然后执行"
echo "    mkdir -p ~/.termux/boot"
echo "    ln -sf $REPO_DIR/run-server.sh ~/.termux/boot/wxauto"
echo
echo "改规则：编辑 core/config.yaml，然后"
echo "    curl -X POST -H \"Authorization: Bearer \$(cat .wxauto_token)\" \\"
echo "         http://127.0.0.1:8848/reload"
echo "============================================================"

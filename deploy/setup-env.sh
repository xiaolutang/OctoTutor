#!/bin/bash
# 初始化远程部署配置（仅在首次部署时运行）
# 生成的 .remote.env 不会被提交到 git
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.remote.env"

if [ -f "$ENV_FILE" ]; then
    echo "✓ $ENV_FILE 已存在，跳过"
    exit 0
fi

cat > "$ENV_FILE" <<'EOF'
# ===== 远程服务器 =====
REMOTE_HOST=your-server-ip
REMOTE_USER=ubuntu
REMOTE_DEPLOY_DIR=/home/ubuntu/project/OctoTutor
REMOTE_PLATFORM=linux/amd64

# ===== 线上 Auth SDK =====
AUTH_CLIENT_ID=bM-IuROa8huhe8Ih
AUTH_BASE_URL=https://auth.xiaolutang.top
EOF

echo "✓ 已生成 $ENV_FILE"
echo ""
echo "  请修改 REMOTE_HOST 为你的服务器 IP："
echo "  vi $ENV_FILE"

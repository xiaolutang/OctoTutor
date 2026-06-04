#!/bin/bash
# OctoTutor 远端一键部署脚本
# 使用方式: ./deploy/remote-deploy.sh [--skip-build]
set -euo pipefail

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 读取配置
ENV_FILE="$SCRIPT_DIR/.remote.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}错误: 未找到 $ENV_FILE${NC}"
    echo -e "${YELLOW}请复制模板并填写: cp deploy/.remote.env.example deploy/.remote.env${NC}"
    exit 1
fi

# 安全解析 .remote.env（不 source，防止 shell 注入）
get_env_var() {
    local name="$1"
    grep -E "^${name}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-
}

REMOTE_HOST=$(get_env_var "REMOTE_HOST")
if [ -z "$REMOTE_HOST" ]; then
    echo -e "${RED}错误: 请在 $ENV_FILE 中填写 REMOTE_HOST${NC}"
    exit 1
fi

REMOTE_USER=$(get_env_var "REMOTE_USER")
REMOTE_USER="${REMOTE_USER:-ubuntu}"
REMOTE_DEPLOY_DIR=$(get_env_var "REMOTE_DEPLOY_DIR")
REMOTE_DEPLOY_DIR="${REMOTE_DEPLOY_DIR:-/home/ubuntu/project/OctoTutor}"
REMOTE_PLATFORM=$(get_env_var "REMOTE_PLATFORM")
REMOTE_PLATFORM="${REMOTE_PLATFORM:-linux/amd64}"
AUTH_CLIENT_ID=$(get_env_var "AUTH_CLIENT_ID")
AUTH_BASE_URL=$(get_env_var "AUTH_BASE_URL")
DASHSCOPE_API_KEY=$(get_env_var "DASHSCOPE_API_KEY")
JWT_SECRET_KEY=$(get_env_var "JWT_SECRET_KEY")
NEWAPI_API_KEY=$(get_env_var "NEWAPI_API_KEY")
FRONTEND_IMAGE="octotutor-frontend:latest"
BACKEND_IMAGE="octotutor-backend:latest"
TMP_FRONTEND="/tmp/octotutor-frontend.tar.gz"
TMP_BACKEND="/tmp/octotutor-backend.tar.gz"

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       OctoTutor 远端一键部署                             ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  服务器: ${GREEN}${REMOTE_USER}@${REMOTE_HOST}${NC}"
echo -e "  部署目录: ${GREEN}${REMOTE_DEPLOY_DIR}${NC}"
echo -e "  目标平台: ${GREEN}${REMOTE_PLATFORM}${NC}"
echo ""

# ===== 0. SSH 连通性检查 =====
echo -e "${YELLOW}[0/5] 检查 SSH 连接...${NC}"
if ! ssh -o ConnectTimeout=5 "${REMOTE_USER}@${REMOTE_HOST}" "echo ok" &>/dev/null; then
    echo -e "${RED}错误: 无法连接 ${REMOTE_USER}@${REMOTE_HOST}${NC}"
    exit 1
fi
echo -e "  ${GREEN}SSH 连接正常${NC}"

# ===== 1. 本地构建 =====
if [[ "${1:-}" != "--skip-build" ]]; then
    echo -e "${YELLOW}[1/5] 构建镜像（平台: ${REMOTE_PLATFORM}）...${NC}"
    cd "$PROJECT_DIR"

    # 准备构建上下文（复制 auth-sdk-web）
    SDK_SOURCE="/Users/tangxiaolu/project/xlfoundryTest/auth-sdk-web"
    if [[ ! -d "$SDK_SOURCE/src" ]]; then
        echo -e "${RED}错误: 未找到 auth-sdk-web 源码: $SDK_SOURCE${NC}"
        exit 1
    fi

    cp -r "$SDK_SOURCE" "$PROJECT_DIR/auth-sdk-web"
    cleanup() { rm -rf "$PROJECT_DIR/auth-sdk-web"; }
    trap cleanup EXIT

    # 构建前端
    echo -e "  ${YELLOW}构建前端...${NC}"
    docker buildx build --platform "$REMOTE_PLATFORM" \
        -f "$SCRIPT_DIR/Dockerfile" \
        --build-arg EXCLUDE_DEV=true \
        -t "$FRONTEND_IMAGE" \
        --load \
        "$PROJECT_DIR"
    echo -e "  ${GREEN}前端构建完成${NC}"

    # 构建后端
    echo -e "  ${YELLOW}构建后端...${NC}"
    docker buildx build --platform "$REMOTE_PLATFORM" \
        -f "$PROJECT_DIR/backend/Dockerfile" \
        -t "$BACKEND_IMAGE" \
        --load \
        "$PROJECT_DIR/backend"
    echo -e "  ${GREEN}后端构建完成${NC}"
else
    echo -e "${YELLOW}[1/5] 跳过构建（使用已有镜像）${NC}"
fi

# 检查镜像
for IMG in "$FRONTEND_IMAGE" "$BACKEND_IMAGE"; do
    if ! docker image inspect "$IMG" &>/dev/null; then
        echo -e "${RED}错误: 镜像 $IMG 不存在${NC}"
        exit 1
    fi
done

# ===== 2. 导出镜像 =====
echo -e "${YELLOW}[2/5] 导出镜像...${NC}"
docker save "$FRONTEND_IMAGE" | gzip > "$TMP_FRONTEND"
FRONTEND_SIZE=$(du -h "$TMP_FRONTEND" | cut -f1)
echo -e "  前端镜像: ${GREEN}${FRONTEND_SIZE}${NC}"

docker save "$BACKEND_IMAGE" | gzip > "$TMP_BACKEND"
BACKEND_SIZE=$(du -h "$TMP_BACKEND" | cut -f1)
echo -e "  后端镜像: ${GREEN}${BACKEND_SIZE}${NC}"

# ===== 3. 传输到服务器 =====
echo -e "${YELLOW}[3/5] 传输到服务器...${NC}"
scp -q "$TMP_FRONTEND" "${REMOTE_USER}@${REMOTE_HOST}:/tmp/octotutor-frontend.tar.gz"
scp -q "$TMP_BACKEND" "${REMOTE_USER}@${REMOTE_HOST}:/tmp/octotutor-backend.tar.gz"
scp -q "$SCRIPT_DIR/docker-compose.yml" "${REMOTE_USER}@${REMOTE_HOST}:/tmp/octotutor-compose.yml"
rm -f "$TMP_FRONTEND" "$TMP_BACKEND"

# ===== 4. 远端加载并启动 =====
echo -e "${YELLOW}[4/5] 远端加载并启动...${NC}"
ssh "${REMOTE_USER}@${REMOTE_HOST}" \
    "REMOTE_DEPLOY_DIR='${REMOTE_DEPLOY_DIR}' AUTH_CLIENT_ID='${AUTH_CLIENT_ID}' AUTH_BASE_URL='${AUTH_BASE_URL}' DASHSCOPE_API_KEY='${DASHSCOPE_API_KEY}' JWT_SECRET_KEY='${JWT_SECRET_KEY}' NEWAPI_API_KEY='${NEWAPI_API_KEY}' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

echo "  加载前端镜像..."
docker load < /tmp/octotutor-frontend.tar.gz
rm -f /tmp/octotutor-frontend.tar.gz

echo "  加载后端镜像..."
docker load < /tmp/octotutor-backend.tar.gz
rm -f /tmp/octotutor-backend.tar.gz

mkdir -p "${REMOTE_DEPLOY_DIR}/deploy"
mv /tmp/octotutor-compose.yml "${REMOTE_DEPLOY_DIR}/deploy/docker-compose.yml"

# 生成 .env 文件供 docker compose 读取
cat > "${REMOTE_DEPLOY_DIR}/.env" <<EOF
AUTH_CLIENT_ID=${AUTH_CLIENT_ID}
AUTH_BASE_URL=${AUTH_BASE_URL}
DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}
JWT_SECRET_KEY=${JWT_SECRET_KEY}
NEWAPI_API_KEY=${NEWAPI_API_KEY}
EOF

cd "${REMOTE_DEPLOY_DIR}"
docker compose -f deploy/docker-compose.yml down 2>/dev/null || true
docker compose -f deploy/docker-compose.yml up -d

echo "  等待服务启动..."
for i in $(seq 1 15); do
    HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/health 2>/dev/null || echo 000)
    if [ "$HTTP_CODE" = "200" ]; then
        echo "  健康检查通过"
        exit 0
    fi
    sleep 2
done
echo "HEALTH_CHECK_FAILED"
REMOTE_SCRIPT

# ===== 5. 输出结果 =====
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                  部署完成！                              ║${NC}"
echo -e "${GREEN}╠═══════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  前端:  http://${REMOTE_HOST}/                          ${NC}"
echo -e "${GREEN}║  服务通过 Traefik 网关路由，确认远端 Traefik 已运行      ${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"

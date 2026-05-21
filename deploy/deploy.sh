#!/bin/bash
# OctoTutor 部署入口
# 使用方式: ./deploy/deploy.sh <command> [options]
#
# 命令:
#   local    本地部署（复用 xlfoundryTest 的 auth-center 网络）
#   remote   远程部署（构建镜像，推送到远程服务器）
#   help     显示帮助信息
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 显示帮助
show_help() {
    echo "OctoTutor 部署工具"
    echo ""
    echo "用法: $0 <command> [options]"
    echo ""
    echo "命令:"
    echo "  local           本地部署（构建 + docker compose up + 健康检查）"
    echo "  remote          远程部署（构建 + 推送到远端服务器）"
    echo "  help            显示此帮助信息"
    echo ""
    echo "本地部署选项:"
    echo "  --no-cache      无缓存构建 Docker 镜像"
    echo "  --skip-build    跳过构建，使用已有镜像"
    echo "  --frontend-only 仅构建/部署前端"
    echo "  --backend-only  仅构建/部署后端"
    echo ""
    echo "远程部署选项:"
    echo "  --skip-build    跳过构建，使用已有镜像"
    echo ""
    echo "前提:"
    echo "  本地部署需要先启动 xlfoundryTest 的 auth-center 服务"
    echo "  cd /path/to/xlfoundryTest && ./deploy/deploy.sh local"
    echo ""
    echo "示例:"
    echo "  $0 local              # 本地一键部署"
    echo "  $0 local --no-cache   # 本地无缓存部署"
    echo "  $0 remote             # 远程一键部署"
    echo "  $0 remote --skip-build # 远程部署（跳过构建）"
}

# ===== local 子命令 =====
do_local() {
    local BUILD_CACHE_FLAG=""
    local SKIP_BUILD=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --no-cache) BUILD_CACHE_FLAG="--no-cache"; shift ;;
            --skip-build) SKIP_BUILD=true; shift ;;
            --frontend-only) BUILD_CACHE_FLAG="$BUILD_CACHE_FLAG --frontend-only"; shift ;;
            --backend-only) BUILD_CACHE_FLAG="$BUILD_CACHE_FLAG --backend-only"; shift ;;
            *) echo "未知参数: $1"; exit 1 ;;
        esac
    done

    # 检查 auth-network-local 是否存在
    if ! docker network inspect auth-network-local &>/dev/null; then
        echo "错误: auth-network-local 网络不存在"
        echo "请先启动 xlfoundryTest 的 auth-center 服务:"
        echo "  cd /Users/tangxiaolu/project/xlfoundryTest && ./deploy/deploy.sh local"
        exit 1
    fi

    # 检查 auth-center 是否健康
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' auth-center 2>/dev/null || echo "unknown")
    if [[ "$HEALTH" != "healthy" ]]; then
        echo "错误: auth-center 未运行或不健康 (状态: $HEALTH)"
        echo "请先启动 xlfoundryTest 的 auth-center 服务:"
        echo "  cd /Users/tangxiaolu/project/xlfoundryTest && ./deploy/deploy.sh local"
        exit 1
    fi

    # 构建镜像
    if [[ "$SKIP_BUILD" != true ]]; then
        echo "==> 构建镜像..."
        bash "$SCRIPT_DIR/build.sh" $BUILD_CACHE_FLAG
    else
        echo "==> 跳过构建（使用已有镜像）"
        if ! docker image inspect octotutor-frontend:latest &>/dev/null; then
            echo "错误: octotutor-frontend:latest 镜像不存在"
            exit 1
        fi
        if ! docker image inspect octotutor-backend:latest &>/dev/null; then
            echo "错误: octotutor-backend:latest 镜像不存在"
            exit 1
        fi
    fi

    # 启动服务
    echo "==> 启动 OctoTutor (compose: deploy/docker-compose.local.yml)..."
    docker compose -f "$SCRIPT_DIR/docker-compose.local.yml" up -d

    # 等待前端就绪
    echo "==> 等待前端服务就绪..."
    local max_wait=30
    local elapsed=0
    while [[ $elapsed -lt $max_wait ]]; do
        if curl -s -o /dev/null -w '%{http_code}' http://octotutor.localhost/ 2>/dev/null | grep -q "200\|302"; then
            echo "  前端已就绪"
            break
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    if [[ $elapsed -ge $max_wait ]]; then
        echo "警告: 前端未在 ${max_wait}s 内就绪"
    fi

    # 等待后端就绪
    echo "==> 等待后端服务就绪..."
    elapsed=0
    while [[ $elapsed -lt $max_wait ]]; do
        BACKEND_STATUS=$(curl -s http://octotutor.localhost/api/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
        if [[ "$BACKEND_STATUS" == "healthy" || "$BACKEND_STATUS" == "unhealthy" ]]; then
            echo "  后端已就绪 (status: $BACKEND_STATUS)"
            break
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    if [[ $elapsed -ge $max_wait ]]; then
        echo "警告: 后端未在 ${max_wait}s 内就绪"
    fi

    echo ""
    echo "==> 服务部署完成!"
    echo ""
    echo "服务地址:"
    echo "  OctoTutor 前端:  http://octotutor.localhost/"
    echo "  OctoTutor 后端:  http://octotutor.localhost/api/health"
    echo "  Auth Center:     http://auth.localhost/"
    echo ""
    exit 0
}

# ===== 子命令分发 =====
COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
    local)
        do_local "$@"
        ;;
    remote)
        exec "$SCRIPT_DIR/remote-deploy.sh" "$@"
        ;;
    help|-h|--help)
        show_help
        exit 0
        ;;
    *)
        echo "未知命令: $COMMAND"
        echo "运行 '$0 help' 查看可用命令"
        exit 1
        ;;
esac

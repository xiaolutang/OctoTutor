#!/bin/bash
# OctoTutor 构建脚本
# 使用方式: ./deploy/build.sh [--no-cache]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CACHE_FLAG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-cache) CACHE_FLAG="--no-cache"; shift ;;
        -h|--help)
            echo "用法: $0 [--no-cache]"
            echo "  --no-cache   无缓存构建 Docker 镜像"
            exit 0 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

# Docker 构建上下文需要包含 auth-sdk-web 源码
# 从 xlfoundryTest 复制到临时目录
SDK_SOURCE="/Users/tangxiaolu/project/xlfoundryTest/auth-sdk-web"
BUILD_CONTEXT="$PROJECT_ROOT"

echo "==> 检查 auth-sdk-web 源码..."
if [[ ! -d "$SDK_SOURCE/src" ]]; then
    echo "错误: 未找到 auth-sdk-web 源码: $SDK_SOURCE"
    exit 1
fi

# 临时复制 SDK 到项目目录用于 Docker 构建
echo "==> 准备构建上下文（复制 auth-sdk-web）..."
cp -r "$SDK_SOURCE" "$BUILD_CONTEXT/auth-sdk-web"

# 构建完成后清理的 trap
cleanup() {
    echo "==> 清理临时文件..."
    rm -rf "$BUILD_CONTEXT/auth-sdk-web"
}
trap cleanup EXIT

echo "==> 构建 octotutor:latest ..."
docker buildx build \
    -f "$SCRIPT_DIR/Dockerfile" \
    -t "octotutor:latest" \
    $CACHE_FLAG \
    --load \
    "$BUILD_CONTEXT"

echo "==> octotutor 构建完成"

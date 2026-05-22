#!/bin/bash
# SSE 集成测试 — 在 Docker 环境中验证异常场景
#
# 用法: bash scripts/test-sse-integration.sh [SCENARIO]
#   SCENARIO: llm-down | embedding-fail | normal | chitchat | all (默认)
#
# 前置条件: deploy/deploy.sh local 已执行，后端容器运行中
# 后置操作: all 模式最后自动恢复正常环境

set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")/.." && pwd)/deploy"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.local.yml"
BACKEND_URL="http://octotutor.localhost"
PASS=0
FAIL=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

assert_contains() {
    local desc="$1" haystack="$2" needle="$3"
    if echo "$haystack" | grep -q "$needle"; then
        echo -e "  ${GREEN}PASS${NC}: $desc"
        ((PASS++))
    else
        echo -e "  ${RED}FAIL${NC}: $desc (expected '$needle')"
        ((FAIL++))
    fi
}

assert_not_contains() {
    local desc="$1" haystack="$2" needle="$3"
    if echo "$haystack" | grep -q "$needle"; then
        echo -e "  ${RED}FAIL${NC}: $desc (unexpected '$needle')"
        ((FAIL++))
    else
        echo -e "  ${GREEN}PASS${NC}: $desc"
        ((PASS++))
    fi
}

# 用 curl + sed 截断读取 SSE 流（解决 SSE 长连接不结束问题）
fetch_sse() {
    local question="$1"
    local max_lines="${2:-15}"
    curl -s -N --max-time 25 -X POST "$BACKEND_URL/api/chat/stream" \
        -H "Content-Type: application/json" \
        -d "{\"question\":\"$question\",\"top_k\":5}" 2>/dev/null | sed -n "1,${max_lines}p"
}

wait_for_backend() {
    echo -e "${YELLOW}  等待后端就绪...${NC}"
    for i in $(seq 1 30); do
        if curl -sf "$BACKEND_URL/api/health" > /dev/null 2>&1; then
            echo "  后端已就绪 (${i}x2s)"
            return 0
        fi
        sleep 2
    done
    echo -e "${RED}  后端未就绪，超时${NC}"
    return 1
}

run_override() {
    local override="$1"
    docker compose -f "$COMPOSE_FILE" -f "$override" \
        up -d --no-deps --force-recreate octotutor-backend 2>&1 | tail -1
}

restore_backend() {
    echo -e "${YELLOW}  恢复正常环境...${NC}"
    bash "$DEPLOY_DIR/deploy.sh" local --backend-only 2>&1 | tail -1
}

# --- I-ERR-01: LLM 不可达 ---
test_llm_down() {
    echo ""
    echo "=== I-ERR-01: LLM 不可达 ==="
    run_override "$DEPLOY_DIR/docker-compose.test-llm-down.yml"
    if ! wait_for_backend; then return; fi

    local resp
    resp=$(fetch_sse "什么是集合？" 10)
    assert_contains "LLM 不可达 → error event" "$resp" "event: error"
    assert_not_contains "LLM 不可达 → 无 done" "$resp" "event: done"
}

# --- I-ERR-02: Embedding 认证失败 ---
test_embedding_fail() {
    echo ""
    echo "=== I-ERR-02: Embedding 认证失败 ==="
    run_override "$DEPLOY_DIR/docker-compose.test-embedding-fail.yml"
    if ! wait_for_backend; then return; fi

    local resp
    resp=$(fetch_sse "什么是集合？" 10)
    assert_contains "Embedding 失败 → error event" "$resp" "event: error"
    assert_contains "Embedding 失败 → error code 02102" "$resp" "02102"
    assert_not_contains "Embedding 失败 → 无 done" "$resp" "event: done"
}

# --- I-ERR-03: 正常数学问题 ---
test_normal() {
    echo ""
    echo "=== I-ERR-03: 正常数学问题 ==="
    restore_backend
    if ! wait_for_backend; then return; fi

    local resp
    resp=$(fetch_sse "什么是集合？" 30)
    assert_contains "正常流程 → retrieving" "$resp" "retrieving"
    assert_contains "正常流程 → sources" "$resp" "event: sources"
    assert_contains "正常流程 → generating" "$resp" "generating"
    assert_contains "正常流程 → token" "$resp" "event: token"
    assert_not_contains "正常流程 → 无 error" "$resp" "event: error"
}

# --- I-ERR-04: 闲聊不检索 ---
test_chitchat() {
    echo ""
    echo "=== I-ERR-04: 闲聊不检索 ==="
    local resp
    resp=$(fetch_sse "你好" 15)
    assert_not_contains "闲聊 → 无 retrieving" "$resp" "retrieving"
    assert_not_contains "闲聊 → 无 sources" "$resp" "event: sources"
    assert_contains "闲聊 → 有 generating" "$resp" "generating"
    assert_contains "闲聊 → 有 token" "$resp" "event: token"
}

# --- 主流程 ---
SCENARIO="${1:-all}"

echo "=== SSE 集成测试 ==="
echo "场景: $SCENARIO"

case "$SCENARIO" in
    llm-down)       test_llm_down ;;
    embedding-fail) test_embedding_fail ;;
    normal)         test_normal ;;
    chitchat)       test_chitchat ;;
    all)
        test_llm_down
        test_embedding_fail
        test_normal
        test_chitchat
        ;;
    *)
        echo "未知场景: $SCENARIO"
        echo "用法: $0 [llm-down|embedding-fail|normal|chitchat|all]"
        exit 1
        ;;
esac

echo ""
echo "=== 结果 ==="
echo -e "  ${GREEN}PASS: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}FAIL: $FAIL${NC}"
    exit 1
else
    echo -e "  FAIL: 0"
fi

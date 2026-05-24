#!/bin/bash
# FB002: 前端鉴权集成冒烟测试
#
# 在 Docker 全栈部署后运行，验证前后端鉴权集成：
#   1. 前端页面加载
#   2. 健康检查公开访问
#   3. 无 token 鉴权拦截
#   4. 有效 token SSE 流
#   5. 过期/无效 token 拒绝
#
# 用法:
#   ./frontend/tests/e2e_auth_smoke.sh
#
# 前提:
#   - Docker 全栈已部署 (deploy/deploy.sh local)
#   - JWT_SECRET_KEY 环境变量已设置
#
set -euo pipefail

# ===== 配置 =====
BASE_URL="http://octotutor.localhost"
JWT_SECRET="${JWT_SECRET_KEY:-}"
PASS=0
FAIL=0
SKIP=0

# ===== 工具函数 =====
pass() { PASS=$((PASS + 1)); echo "  [PASS] $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  [FAIL] $1"; }
skip() { SKIP=$((SKIP + 1)); echo "  [SKIP] $1"; }
info() { echo "  [INFO] $1"; }

# ===== 前置检查 =====
echo "========================================"
echo "FB002: 前端鉴权集成冒烟测试"
echo "========================================"
echo ""

# 检查 JWT_SECRET_KEY
if [ -z "$JWT_SECRET" ]; then
    echo "错误: JWT_SECRET_KEY 环境变量未设置"
    echo "  export JWT_SECRET_KEY=your-secret-key"
    exit 1
fi

# 检查 python3 + PyJWT
if ! python3 -c "import jwt" 2>/dev/null; then
    echo "错误: 需要 python3 + PyJWT 库"
    echo "  pip install PyJWT"
    exit 1
fi

# 检查服务可达性
if ! curl -s -o /dev/null -w '' "${BASE_URL}/" 2>/dev/null; then
    echo "错误: ${BASE_URL} 不可达"
    echo "  请先部署: ./deploy/deploy.sh local"
    exit 1
fi

echo "--- 前置检查通过 ---"
echo ""

# ===== 测试用例 =====

# ----- Test 1: 前端页面加载 -----
echo "Test 1: 前端页面加载 (GET /)"
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/" 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    pass "前端页面返回 200"
else
    fail "前端页面返回 $HTTP_CODE (期望 200)"
fi

# 检查 HTML 内容
HTML_CONTENT=$(curl -s "${BASE_URL}/" 2>/dev/null)
if echo "$HTML_CONTENT" | grep -q '_next'; then
    pass "HTML 包含 _next 资源引用"
else
    fail "HTML 不包含 _next 资源引用"
fi

# 检查 JS 资源可达
JS_CHUNK=$(echo "$HTML_CONTENT" | grep -o '_next/static/chunks/[^"]*\.js' | head -1)
if [ -n "$JS_CHUNK" ]; then
    JS_CODE=$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/${JS_CHUNK}" 2>/dev/null)
    if [ "$JS_CODE" = "200" ]; then
        pass "JS 资源可达: ${JS_CHUNK}"
    else
        fail "JS 资源不可达: ${JS_CHUNK} (HTTP $JS_CODE)"
    fi
else
    skip "未找到 JS chunk URL"
fi
echo ""

# ----- Test 2: 健康检查公开访问 -----
echo "Test 2: 健康检查公开访问 (GET /api/health 无 token)"
HEALTH_RESPONSE=$(curl -s "${BASE_URL}/api/health" 2>/dev/null)
HEALTH_CODE=$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/api/health" 2>/dev/null)

if [ "$HEALTH_CODE" = "200" ]; then
    pass "/api/health 返回 200 (无需鉴权)"
else
    fail "/api/health 返回 $HEALTH_CODE (期望 200)"
fi

# 验证响应结构
if echo "$HEALTH_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'status' in d; assert 'chromadb' in d" 2>/dev/null; then
    pass "/api/health 响应结构正确 (status + chromadb)"
else
    fail "/api/health 响应结构异常"
fi
echo ""

# ----- Test 3: 无 token 鉴权拦截 -----
echo "Test 3: 无 token 鉴权拦截 (POST /api/chat/stream)"
NO_AUTH_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE_URL}/api/chat/stream" \
    -H 'Content-Type: application/json' \
    -d '{"question":"test"}' 2>/dev/null)
if [ "$NO_AUTH_CODE" = "401" ]; then
    pass "无 token 返回 401 Unauthorized"
else
    fail "无 token 返回 $NO_AUTH_CODE (期望 401)"
fi

# 验证响应 body
NO_AUTH_BODY=$(curl -s -X POST "${BASE_URL}/api/chat/stream" \
    -H 'Content-Type: application/json' \
    -d '{"question":"test"}' 2>/dev/null)
if echo "$NO_AUTH_BODY" | grep -qi "auth\|token\|unauthorized\|missing"; then
    pass "401 响应包含鉴权错误信息"
else
    info "401 响应内容: $(echo "$NO_AUTH_BODY" | head -c 200)"
fi
echo ""

# ----- Test 4: 有效 token SSE 流 -----
echo "Test 4: 有效 token SSE 流 (POST /api/chat/stream)"
VALID_TOKEN=$(python3 -c "
import jwt, time
payload = {
    'sub': 'smoke-test-user',
    'client_id': 'smoke-test',
    'type': 'access',
    'iat': int(time.time()),
    'exp': int(time.time()) + 3600
}
print(jwt.encode(payload, '$JWT_SECRET', algorithm='HS256'))
")

# 先检查鉴权是否通过
AUTH_PASS_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST "${BASE_URL}/api/chat/stream" \
    -H "Authorization: Bearer ${VALID_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d '{"question":"test"}' 2>/dev/null)
if [ "$AUTH_PASS_CODE" = "200" ]; then
    pass "有效 token 返回 200"
else
    fail "有效 token 返回 $AUTH_PASS_CODE (期望 200)"
fi

# 验证 SSE 格式
SSE_RESPONSE=$(curl -s -N --max-time 30 -X POST "${BASE_URL}/api/chat/stream" \
    -H "Authorization: Bearer ${VALID_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d '{"question":"什么是操作系统？"}' 2>&1)

if echo "$SSE_RESPONSE" | grep -q "^event: "; then
    pass "SSE 包含 event: 行"
else
    fail "SSE 缺少 event: 行"
fi

if echo "$SSE_RESPONSE" | grep -q "^data: "; then
    pass "SSE 包含 data: 行"
else
    fail "SSE 缺少 data: 行"
fi

# 验证 Content-Type
CONTENT_TYPE=$(curl -s -o /dev/null -w '%{content_type}' --max-time 10 -X POST "${BASE_URL}/api/chat/stream" \
    -H "Authorization: Bearer ${VALID_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d '{"question":"test"}' 2>/dev/null)
if echo "$CONTENT_TYPE" | grep -q "text/event-stream"; then
    pass "Content-Type 为 text/event-stream"
else
    fail "Content-Type 为 $CONTENT_TYPE (期望 text/event-stream)"
fi

# 检查是否包含检索或错误事件（说明鉴权通过后流正常启动）
if echo "$SSE_RESPONSE" | grep -q "event: status\|event: error\|event: message"; then
    pass "SSE 流正常产出事件"
else
    info "SSE 事件: $(echo "$SSE_RESPONSE" | head -c 300)"
fi
echo ""

# ----- Test 5: 过期 token 拒绝 -----
echo "Test 5: 过期 token 拒绝"
EXPIRED_TOKEN=$(python3 -c "
import jwt, time
payload = {
    'sub': 'smoke-test-user',
    'client_id': 'smoke-test',
    'type': 'access',
    'iat': int(time.time()) - 7200,
    'exp': int(time.time()) - 3600
}
print(jwt.encode(payload, '$JWT_SECRET', algorithm='HS256'))
")

EXPIRED_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE_URL}/api/chat/stream" \
    -H "Authorization: Bearer ${EXPIRED_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d '{"question":"test"}' 2>/dev/null)
if [ "$EXPIRED_CODE" = "401" ]; then
    pass "过期 token 返回 401"
else
    fail "过期 token 返回 $EXPIRED_CODE (期望 401)"
fi
echo ""

# ----- Test 6: 无效签名 token 拒绝 -----
echo "Test 6: 无效签名 token 拒绝"
INVALID_SIG_TOKEN=$(python3 -c "
import jwt, time
payload = {
    'sub': 'smoke-test-user',
    'client_id': 'smoke-test',
    'type': 'access',
    'iat': int(time.time()),
    'exp': int(time.time()) + 3600
}
print(jwt.encode(payload, 'wrong-secret-key-not-the-real-one', algorithm='HS256'))
")

INVALID_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE_URL}/api/chat/stream" \
    -H "Authorization: Bearer ${INVALID_SIG_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d '{"question":"test"}' 2>/dev/null)
if [ "$INVALID_CODE" = "401" ]; then
    pass "无效签名 token 返回 401"
else
    fail "无效签名 token 返回 $INVALID_CODE (期望 401)"
fi
echo ""

# ----- Test 7: 错误 token type 拒绝 -----
echo "Test 7: refresh token 类型被拒绝"
REFRESH_TOKEN=$(python3 -c "
import jwt, time
payload = {
    'sub': 'smoke-test-user',
    'client_id': 'smoke-test',
    'type': 'refresh',
    'iat': int(time.time()),
    'exp': int(time.time()) + 3600
}
print(jwt.encode(payload, '$JWT_SECRET', algorithm='HS256'))
")

REFRESH_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE_URL}/api/chat/stream" \
    -H "Authorization: Bearer ${REFRESH_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d '{"question":"test"}' 2>/dev/null)
if [ "$REFRESH_CODE" = "401" ]; then
    pass "refresh token 返回 401"
else
    fail "refresh token 返回 $REFRESH_CODE (期望 401)"
fi
echo ""

# ===== 汇总 =====
echo "========================================"
TOTAL=$((PASS + FAIL + SKIP))
echo "测试结果: ${PASS}/${TOTAL} 通过, ${FAIL} 失败, ${SKIP} 跳过"
echo "========================================"

if [ "$FAIL" -gt 0 ]; then
    echo "STATUS: FAIL"
    exit 1
else
    echo "STATUS: ALL PASS"
    exit 0
fi

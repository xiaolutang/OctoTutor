#!/bin/bash
# BB002: E2E 鉴权冒烟测试
# 验证 JWT 鉴权在 Docker 环境中的集成行为
#
# 前提:
#   - xlfoundryTest auth-center 已启动
#   - OctoTutor 后端已通过 deploy.sh local --backend-only 部署
#   - JWT_SECRET_KEY 环境变量已设置（或通过 .env 文件）
#
# 使用方式:
#   # 从 OctoTutor 根目录执行
#   JWT_SECRET_KEY=xxx bash backend/tests/e2e_auth_smoke.sh
set -euo pipefail

BASE_URL="http://octotutor.localhost"
JWT_SECRET="${JWT_SECRET_KEY:?JWT_SECRET_KEY 环境变量未设置}"

PASS=0
FAIL=0
RESULTS=()

report() {
    local name="$1" expected="$2" actual="$3"
    local pass=false
    if [[ "$expected" == "non-401" ]]; then
        [[ "$actual" != "401" ]] && pass=true
    else
        [[ "$actual" == "$expected" ]] && pass=true
    fi
    if $pass; then
        PASS=$((PASS + 1))
        RESULTS+=("PASS  $name (expected=$expected, got=$actual)")
    else
        FAIL=$((FAIL + 1))
        RESULTS+=("FAIL  $name (expected=$expected, got=$actual)")
    fi
}

# ── 生成 token ─────────────────────────────────────
generate_token() {
    local exp="${1:-$(($(date +%s) + 3600))}"
    python3 -c "
from jose import jwt
import time
payload = {
    'sub': 'user-123',
    'client_id': 'testuser',
    'exp': $exp,
    'type': 'access'
}
print(jwt.encode(payload, '$JWT_SECRET', algorithm='HS256'))
"
}

VALID_TOKEN=$(generate_token)
EXPIRED_TOKEN=$(generate_token 1)

echo "=== E2E Auth Smoke Test ==="
echo "BASE_URL: $BASE_URL"
echo "JWT_SECRET: ${JWT_SECRET:0:8}..."
echo ""

# ── T1: 无 token POST /api/chat → 401 ─────────────
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/chat" \
    -H 'Content-Type: application/json' -d '{"question":"test"}')
report "T1: no-token POST /api/chat" "401" "$CODE"

# ── T2: 无 token POST /api/chat/stream → 401 ──────
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/chat/stream" \
    -H 'Content-Type: application/json' -d '{"question":"test"}')
report "T2: no-token POST /api/chat/stream" "401" "$CODE"

# ── T3: 无 token POST /api/retrieve → 401 ─────────
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/retrieve" \
    -H 'Content-Type: application/json' -d '{"query":"test"}')
report "T3: no-token POST /api/retrieve" "401" "$CODE"

# ── T4: 无 token GET /api/health → 200 ─────────────
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/health")
report "T4: no-token GET /api/health" "200" "$CODE"

# ── T5: 过期 token POST /api/chat → 401 ────────────
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/chat" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $EXPIRED_TOKEN" \
    -d '{"question":"test"}')
report "T5: expired-token POST /api/chat" "401" "$CODE"

# ── T6: 过期 token POST /api/retrieve → 401 ────────
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/retrieve" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $EXPIRED_TOKEN" \
    -d '{"query":"test"}')
report "T6: expired-token POST /api/retrieve" "401" "$CODE"

# ── T7: 有效 token POST /api/chat → 非 401 ────────
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/chat" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $VALID_TOKEN" \
    -d '{"question":"test"}')
report "T7: valid-token POST /api/chat" "non-401" "$CODE"

# ── T8: 有效 token POST /api/chat/stream → 非 401 ─
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/chat/stream" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $VALID_TOKEN" \
    -d '{"question":"test"}')
report "T8: valid-token POST /api/chat/stream" "non-401" "$CODE"

# ── T9: 有效 token POST /api/retrieve → 非 401 ────
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/retrieve" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $VALID_TOKEN" \
    -d '{"query":"test"}')
report "T9: valid-token POST /api/retrieve" "non-401" "$CODE"

# ── 结果汇总 ────────────────────────────────────────
echo "=== Results ==="
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""
echo "PASS: $PASS / $((PASS + FAIL))"

if [[ $FAIL -gt 0 ]]; then
    echo "FAILED: $FAIL tests"
    exit 1
fi
echo "All tests passed!"

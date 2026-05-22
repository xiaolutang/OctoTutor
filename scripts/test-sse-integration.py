#!/usr/bin/env python3
"""SSE 集成测试 — 在 Docker 容器外通过 Traefik 验证异常场景

用法:
  python3 scripts/test-sse-integration.py [--internal]

  --internal: 在容器内直接访问 localhost:8000（绕过 Traefik）
"""
import json
import subprocess
import sys
import time
import urllib.request

BACKEND_URL_EXTERNAL = "http://octotutor.localhost"
BACKEND_URL_INTERNAL = "http://localhost:8000"
DEPLOY_DIR = "deploy"
COMPOSE_FILE = f"{DEPLOY_DIR}/docker-compose.local.yml"

PASS = 0
FAIL = 0


def log_pass(msg):
    global PASS
    PASS += 1
    print(f"  \033[0;32mPASS\033[0m: {msg}")


def log_fail(msg):
    global FAIL
    FAIL += 1
    print(f"  \033[0;31mFAIL\033[0m: {msg}")


def assert_contains(desc, haystack, needle):
    if needle in haystack:
        log_pass(desc)
    else:
        log_fail(f"{desc} (expected '{needle}')")


def assert_not_contains(desc, haystack, needle):
    if needle not in haystack:
        log_pass(desc)
    else:
        log_fail(f"{desc} (unexpected '{needle}')")


def fetch_sse(url, question, timeout=20):
    data = json.dumps({"question": question, "top_k": 5}).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()[:2000]
    except Exception as e:
        return f"ERROR: {e}"


def run_compose_override(override_file):
    subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "-f", override_file,
         "up", "-d", "--no-deps", "--force-recreate", "octotutor-backend"],
        check=True, capture_output=True,
    )


def restore_backend():
    subprocess.run(
        ["bash", f"{DEPLOY_DIR}/deploy.sh", "local", "--backend-only"],
        check=True, capture_output=True,
    )


def wait_for_backend(url, max_wait=60):
    print("  等待后端就绪...")
    for _ in range(max_wait // 2):
        try:
            urllib.request.urlopen(f"{url}/api/health", timeout=5)
            print("  后端已就绪")
            return True
        except Exception:
            time.sleep(2)
    print("  \033[0;31m后端未就绪，超时\033[0m")
    return False


def test_llm_down(url):
    print("\n=== I-ERR-01: LLM 不可达 ===")
    print("  启动异常环境 (NEWAPI_BASE_URL=localhost:1)...")
    run_compose_override(f"{DEPLOY_DIR}/docker-compose.test-llm-down.yml")

    if not wait_for_backend(url):
        return

    time.sleep(2)
    resp = fetch_sse(f"{url}/api/chat/stream", "什么是集合？")

    assert_contains("LLM 不可达 → SSE error event", resp, "event: error")
    # 可能是 02201 (LLM_CONNECT_FAILED) 或 02202 (LLM_STREAM_ERROR)
    has_error_code = "02201" in resp or "02202" in resp
    if has_error_code:
        log_pass("LLM 不可达 → error code (02201 或 02202)")
    else:
        log_fail("LLM 不可达 → error code (02201 或 02202)")
    assert_not_contains("LLM 不可达 → 无 done event", resp, "event: done")


def test_embedding_fail(url):
    print("\n=== I-ERR-02: Embedding 认证失败 ===")
    print("  启动异常环境 (DASHSCOPE_API_KEY=invalid)...")
    run_compose_override(f"{DEPLOY_DIR}/docker-compose.test-embedding-fail.yml")

    if not wait_for_backend(url):
        return

    time.sleep(2)
    resp = fetch_sse(f"{url}/api/chat/stream", "什么是集合？")

    assert_contains("Embedding 失败 → SSE error event", resp, "event: error")
    assert_contains("Embedding 失败 → error code 02102", resp, "02102")
    assert_not_contains("Embedding 失败 → 无 done event", resp, "event: done")


def test_normal(url):
    print("\n=== I-ERR-03: 正常数学问题 ===")
    print("  恢复正常环境...")
    restore_backend()

    if not wait_for_backend(url):
        return

    resp = fetch_sse(f"{url}/api/chat/stream", "什么是集合？")

    assert_contains("正常流程 → status retrieving", resp, "retrieving")
    assert_contains("正常流程 → sources event", resp, "event: sources")
    assert_contains("正常流程 → status generating", resp, "generating")
    assert_contains("正常流程 → token event", resp, "event: token")
    assert_contains("正常流程 → done event", resp, "event: done")
    assert_not_contains("正常流程 → 无 error event", resp, "event: error")


def test_chitchat(url):
    print("\n=== I-ERR-04: 闲聊不检索 ===")
    resp = fetch_sse(f"{url}/api/chat/stream", "你好")

    assert_not_contains("闲聊 → 无 retrieving", resp, "retrieving")
    assert_not_contains("闲聊 → 无 sources", resp, "event: sources")
    assert_contains("闲聊 → 有 generating", resp, "generating")
    assert_contains("闲聊 → 有 token", resp, "event: token")
    assert_contains("闲聊 → 有 done", resp, "event: done")


if __name__ == "__main__":
    use_internal = "--internal" in sys.argv
    url = BACKEND_URL_INTERNAL if use_internal else BACKEND_URL_EXTERNAL

    print(f"=== SSE 集成测试 ===")
    print(f"模式: {'容器内 (localhost:8000)' if use_internal else '外部 (Traefik)'}")

    test_llm_down(url)
    test_embedding_fail(url)
    test_normal(url)
    test_chitchat(url)

    print(f"\n=== 结果 ===")
    print(f"  \033[0;32mPASS: {PASS}\033[0m")
    if FAIL > 0:
        print(f"  \033[0;31mFAIL: {FAIL}\033[0m")
        sys.exit(1)
    else:
        print(f"  FAIL: 0")

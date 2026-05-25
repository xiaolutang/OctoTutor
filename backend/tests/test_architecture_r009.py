"""
R009-BB004: architecture.md 内容完整性检查

验证 .dev-flow/architecture.md 在 R009 变更后的关键内容约束：
  1. 拓扑部分不再包含 SQLite
  2. 关键决策部分包含 SQLAlchemy
  3. 权威边界部分包含 /api/conversations
  4. SSE 事件 type 列表包含 title
  5. 禁止模式部分不含 R006 条目
"""
from pathlib import Path

import pytest

ARCH_PATH = Path(__file__).resolve().parent.parent.parent / ".dev-flow" / "architecture.md"


@pytest.fixture(scope="module")
def arch_content() -> str:
    """读取 architecture.md 全文。"""
    assert ARCH_PATH.exists(), f"architecture.md 不存在: {ARCH_PATH}"
    return ARCH_PATH.read_text(encoding="utf-8")


def _section(content: str, heading: str) -> str:
    """提取 markdown 中某个 ## 级别标题下的内容块（直到下一个 ## 或文件末尾）。"""
    lines = content.splitlines()
    in_section = False
    section_lines: list[str] = []

    for line in lines:
        if line.strip().startswith("## ") and not in_section:
            if heading in line:
                in_section = True
            continue
        if line.strip().startswith("## ") and in_section:
            break
        if in_section:
            section_lines.append(line)

    return "\n".join(section_lines)


# ── 场景 1: 拓扑无 SQLite ──────────────────────────────────────────

class TestTopologyNoSQLite:
    def test_topology_excludes_sqlite(self, arch_content: str):
        topo = _section(arch_content, "系统拓扑")
        assert "SQLite" not in topo, (
            "系统拓扑部分不应包含 SQLite 引用（已迁移至 PostgreSQL）"
        )


# ── 场景 2: 关键决策含 SQLAlchemy ──────────────────────────────────

class TestKeyDecisionsContainSQLAlchemy:
    def test_decisions_contain_sqlalchemy(self, arch_content: str):
        decisions = _section(arch_content, "关键决策")
        assert "SQLAlchemy" in decisions, (
            "关键决策部分应包含 SQLAlchemy（R009 ORM 选型）"
        )


# ── 场景 3: 权威边界含 conversations ──────────────────────────────

class TestAuthorityBoundaryConversations:
    def test_boundary_contains_conversations_api(self, arch_content: str):
        boundary = _section(arch_content, "权威边界")
        assert "/api/conversations" in boundary, (
            "权威边界部分应包含 /api/conversations 路径"
        )


# ── 场景 4: 不变量含 title 事件 ────────────────────────────────────

class TestInvariantContainsTitleEvent:
    def test_sse_events_include_title(self, arch_content: str):
        invariants = _section(arch_content, "不变量")
        # 找 SSE 事件 type 行并验证包含 title
        assert "title" in invariants, (
            "不变量部分 SSE 事件 type 列表应包含 title"
        )


# ── 场景 5: 禁止模式无 R006 条目 ──────────────────────────────────

class TestProhibitionsNoR006:
    def test_prohibitions_exclude_r006(self, arch_content: str):
        prohibitions = _section(arch_content, "禁止模式")
        assert "R006" not in prohibitions, (
            "禁止模式部分不应包含 R006 相关条目"
        )

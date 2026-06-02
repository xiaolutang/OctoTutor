---
version: "1.0"
type: tasks
topic: classifier-default-fix
requirement_cycle: R010
workflow:
  evaluate_provider: local
  mode: auto
status: archived
---

# 分类器默认策略修正 — 后端任务清单

基于 `.dev-flow/R010/analysis/2026-05-28--classifier-default-fix-design.md` 设计，将分类器修复拆为 2 个任务。

全局约束：
- 只改 classifier.py + test_question_classifier.py，不动 nodes.py / graph.py
- 分类逻辑变更顺序：扩展问候词 → 加社交噪音检测 → 加数学关键词 → 改默认返回值
- 参考现有分类器：`backend/app/domain/classifier.py`
- 参考现有测试：`backend/tests/test_question_classifier.py`

---

## 执行顺序

1. ⬜ R010-BB006 — classifier.py 分类逻辑修正（无依赖）
   - ⬜ BB006.1 扩展 _GREETING_PATTERNS + 新增社交噪音检测
   - ⬜ BB006.2 补充 _MATH_KEYWORDS
   - ⬜ BB006.3 修改默认返回值 + 更新文档注释
2. ⬜ R010-BB007 — test_question_classifier.py 测试对齐（依赖 BB006）
   - ⬜ BB007.1 修正因默认翻转而失败的 3 个测试
   - ⬜ BB007.2 新增负面/正面用例测试

---

## R010-BB006：classifier.py — 分类逻辑修正 `✅ 已完成`

- 文件：`backend/app/domain/classifier.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - "你好你好" → unrelated（社交噪音检测）
  - "哈哈哈哈" → unrelated（社交噪音检测）
  - "这道题怎么做" → textbook（"题"关键词命中）
  - "帮我算一下" → textbook（"算"关键词命中）
  - "今天天气怎么样" → unrelated（默认 unrelated）
  - "背诵一下将进酒" → unrelated（默认 unrelated）
  - 无 lint 错误：`ruff check app/domain/classifier.py`
- test_tasks:
  - type: unit
    description: 分类器单元测试验证
    scenarios: [重复问候, 社交笑声, 新关键词, 非数学默认]
- contract_refs: []
- decision_refs: []
- blocked_files: [backend/app/agent/nodes.py, backend/app/agent/graph.py]

### BB006.1 扩展 _GREETING_PATTERNS + 新增社交噪音检测 `⬜`

**问候词表扩展**：在 `_GREETING_PATTERNS` 中追加 6 个社交噪音模式

```python
# _GREETING_PATTERNS 追加:
"哈哈", "呵呵", "嘿嘿", "嘻嘻",   # 社交笑声
"嗯嗯", "哦哦",                    # 重复语气词
```

**社交噪音检测**：在精确问候匹配（步骤 2）之后、数学符号检查（步骤 3）之前，新增步骤 2b

```python
# 2b. 社交噪音检测（去问候后残余为空 → 纯噪音）
cleaned = normalized
for g in _GREETING_PATTERNS:
    cleaned = cleaned.replace(g, "")
cleaned = cleaned.strip("。！？!?. ")
if not cleaned:
    return "unrelated"
```

安全边界验证：
- "你好你好" → remove "你好"×2 → "" → unrelated ✓
- "哈哈哈哈" → remove "哈哈"×2 → "" → unrelated ✓
- "你好请问函数" → remove "你好" → "请问函数" ≠ "" → 继续到关键词检查 ✓

### BB006.2 补充 _MATH_KEYWORDS `⬜`

在 `_MATH_KEYWORDS` 中追加 2 个高置信度数学上下文关键词

```python
# _MATH_KEYWORDS 追加:
"题",   # "这道题"、"做几道题"、"题目"
"算",   # "帮我算一下"、"怎么算"、"算出"
```

### BB006.3 修改默认返回值 + 更新文档注释 `⬜`

```python
# 文件顶部注释，第 12 行:
# 旧: 5. 默认 → textbook（宁可多检索，不漏检索）
# 新: 5. 默认 → unrelated（宁可拒答，不误答）

# 第 80 行:
# 旧: return "textbook"
# 新: return "unrelated"
```

---

## R010-BB007：test_question_classifier.py — 测试对齐 `✅ 已完成`

- 文件：`backend/tests/test_question_classifier.py`
- 改动类型：修改
- domain: backend
- task_layer: business
- depends_on: [R010-BB006]
- priority: 5
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 全部测试通过：`pytest tests/test_question_classifier.py -v`
  - 现有 12 个 textbook 用例不受影响
  - 新增 5 个测试覆盖社交噪音和新关键词场景
- test_tasks:
  - type: unit
    description: 分类器单元测试
    scenarios: [全部分类场景回归]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### BB007.1 修正因默认翻转而失败的 3 个测试 `⬜`

| 测试方法 | 输入 | 旧期望 | 新期望 | 理由 |
|----------|------|--------|--------|------|
| `test_exactly_4_chars` | "帮我看看" | textbook | **unrelated** | 4 字无数学关键词，默认改 unrelated |
| `test_non_math_long_text` | "今天天气怎么样" | textbook | **unrelated** | 非数学话题，默认改 unrelated |

注：`test_default_fallback`（"帮我看看这道题"）仍期望 textbook，因 BB006.2 新增 "题" 关键词命中。

### BB007.2 新增负面/正面用例测试 `⬜`

在 `TestUnrelatedIntent` 中新增：

```python
def test_repeated_greeting(self):
    assert classify_question("你好你好") == "unrelated"

def test_social_laughter(self):
    assert classify_question("哈哈哈哈") == "unrelated"

def test_non_math_poetry(self):
    assert classify_question("背诵一下将进酒") == "unrelated"
```

在 `TestTextbookIntent` 中新增：

```python
def test_math_exercise_keyword(self):
    assert classify_question("这道题怎么做") == "textbook"

def test_calculate_keyword(self):
    assert classify_question("帮我算一下") == "textbook"
```

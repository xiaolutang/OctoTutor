---
module: conversation-utils
version: "1.0"
date: 2026-06-03
tags: [refactoring, backend]
type: design_backend
status: designed
requirement_cycle: R013
source_analysis: 2026-06-03--code-quality-governance.md
architecture_md_updates: false
---

# 对话工具函数提取 — 后端设计

> 从 conversation_router.py 提取共享函数到独立模块

## 1. 目标

- 消除 stream_router.py 对 conversation_router.py 私有函数的跨模块依赖
- 将 `_load_conversation_by_id` 和 `_to_api_message` 移到 `app/chat/conversation_utils.py`

## 2. 现状

`stream_router.py:28` 导入：
```python
from app.chat.conversation_router import _load_conversation_by_id, _to_api_message
```

这两个函数以下划线前缀标记为私有，但被跨模块使用，违反模块边界。

## 3. 项目结构

```
app/chat/
├── conversation_utils.py    # 新建：共享工具函数
├── conversation_router.py   # 改动：import 从本地改为从 utils
└── stream_router.py         # 改动：import 从 conversation_router 改为从 utils
```

## 4. 具体改动

### conversation_utils.py（新建）

从 conversation_router.py 移入：
- `load_conversation_by_id`（去掉下划线前缀，标注为公共 API）
- `to_api_message`（去掉下划线前缀，标注为公共 API）

### conversation_router.py（修改）

- 删除这两个函数的定义
- 改为 `from app.chat.conversation_utils import load_conversation_by_id, to_api_message`
- 内部调用不变（函数名去掉下划线，全局替换）

### stream_router.py（修改）

- 改为 `from app.chat.conversation_utils import load_conversation_by_id, to_api_message`

## 5. 验收标准

| 验收条件 | 验收方式 |
|----------|----------|
| conversation_utils.py 存在且包含两个公共函数 | 文件检查 |
| conversation_router.py 和 stream_router.py 从 utils 导入 | grep 检查 |
| 无跨路由私有函数导入 | `grep "_load_conversation\|_to_api_message" stream_router.py` 无结果 |
| 后端测试全部通过 | `python3 -m pytest` |

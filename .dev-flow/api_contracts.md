# API 契约 — R003

> updated: 2026-05-20

## GET /api/health

健康检查端点，返回 ChromaDB 连接状态和文档数量。

### Request

```
GET /api/health
```

### Response 200

```json
{
  "status": "healthy",
  "chromadb": {
    "connected": true,
    "document_count": 3420
  },
  "embedding": {
    "available": true
  }
}
```

### 错误场景

| 场景 | 状态码 | 响应 |
|------|--------|------|
| ChromaDB 未连接 | 200 | `{"status": "unhealthy", "chromadb": {"connected": false, "document_count": 0}}` |
| ChromaDB 为空 | 200 | `{"status": "healthy", "chromadb": {"connected": true, "document_count": 0}}` |

## POST /api/retrieve

向量检索端点，基于 cosine similarity 返回 top-K 相关 chunks。

### Request

```json
{
  "query": "二次函数的顶点公式",
  "top_k": 5
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| query | string | 是 | - | 查询文本 |
| top_k | int | 否 | 5 | 返回数量，1-20 |

### Response 200

```json
{
  "chunks": [
    {
      "chunk_id": "必修第一册::1.3二次函数::p45_s0::child::2",
      "text": "二次函数 $f(x)=ax^2+bx+c$ 的顶点坐标为...",
      "score": 0.89,
      "metadata": {
        "book": "必修第一册",
        "chapter": "第一章 集合与函数概念",
        "section": "1.3 二次函数",
        "page": 45,
        "chunk_type": "child",
        "has_formula": true,
        "parent_id": "必修第一册::1.3二次函数::p45_s0::parent",
        "child_index": 2
      }
    }
  ],
  "total": 5
}
```

### 错误场景

| 场景 | 状态码 | 响应 |
|------|--------|------|
| 无结果 | 200 | `{"chunks": [], "total": 0}` |
| 缺少 query | 422 | 验证错误详情 |
| ChromaDB 为空 | 200 | `{"chunks": [], "total": 0}` |

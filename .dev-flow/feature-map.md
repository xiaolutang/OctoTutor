# 项目功能图

## 模块依赖图

```mermaid
graph LR
    User[用户] --> ChatUI[Chat UI]
    ChatUI --> SSEHook[useChatStream]
    SSEHook --> ApiClient[apiClient 统一网络层]
    ApiClient --> SSEEndpoint[SSE /api/chat/stream]
    ApiClient --> TokenMgr[TokenManager]

    Dev[开发者] --> ChatAPI[POST /api/chat]

    SSEEndpoint --> AuthMiddleware[JWT 鉴权 Depends]
    ChatAPI --> AuthMiddleware
    RetrieveAPI[POST /api/retrieve] --> AuthMiddleware
    AuthMiddleware --> Retrieve[混合检索+Rerank]
    ChatAPI --> Retrieve
    Retrieve --> Embedding[DashScopeEmbedding]
    Retrieve --> VectorStore[ChromaDBStore]
    Retrieve --> BM25[BM25Retriever]
    Retrieve --> Reranker[Reranker]

    AuthMiddleware --> Generator[Generator]
    Generator --> LLM[OpenAI 兼容 LLM]

    TokenMgr -.-> AuthCenter[auth-center]

    EvalCLI --> CPEval[Context Precision Eval]
    EvalCLI --> FaithEval[Faithfulness Eval]
    CPEval --> Retrieve
    FaithEval --> Retrieve
    FaithEval --> Generator
    FaithEval --> LLM

    Embedding -.-> DashScope[DashScope API]
    Reranker -.-> DashScope
    VectorStore -.-> ChromaDB[(ChromaDB)]
    BM25 -.-> ChromaDB
    LLM -.-> NewAPI[NewAPI 配置切换]

    Ingestion[Ingestion Pipeline] --> Embedding
    Ingestion --> VectorStore
    Ingestion --> Chunker[MathChunker]
    Chunker --> PDFReader[PDF Reader]

    style ApiClient fill:#90CAF9
    style TokenMgr fill:#90CAF9
    style AuthMiddleware fill:#A5D6A7
```

## 颜色分级

| 颜色 | 前缀 | 含义 |
|------|------|------|
| 🔵 蓝色 | FF | 前端基础（apiClient, TokenManager） |
| 🟢 绿色 | BF | 后端基础（AuthMiddleware） |
| 🟡 黄色 | BB | 后端业务（Router Depends 注入） |
| 🟠 橙色 | FB | 前端业务（useChatStream 改用 apiClient） |

---
version: "1.0"
type: tasks
topic: validation-i18n
requirement_cycle: R018
workflow:
  evaluate_provider: local
  mode: direct
plan_format_exemption: true
status: archived
---

# 全局 422 错误中文化 — 任务清单

auth-center 的 Pydantic 字段校验错误（422）返回英文原始信息，前端用户看到不可读内容。
全局拦截 422，统一翻译为中文，返回与 BaseAPIException 一致的 `{"detail": "中文消息"}` 格式。

---

## 执行顺序

1. ✅ 任务 1 — main.py 添加 RequestValidationError 全局异常处理器（无依赖）
2. ✅ 任务 2 — test_register.py 更新 T16-T18 断言（无依赖）
3. ✅ 任务 3 — test_validation.py 新建全局 handler 独立测试（无依赖）
4. ✅ 任务 4 — 部署验证（依赖任务 1-3）

---

## 任务 1：main.py 全局异常处理器 `✅ 已完成`

- 文件：`xlfoundryTest/auth-center/app/main.py`
- 改动：添加 `_FIELD_NAMES` 字段名中文映射 + `_translate_validation_error` 翻译函数 + `validation_exception_handler` 全局异常处理器
- acceptance_criteria:
  - ✅ 422 返回 `{"detail": "中文消息"}` 格式（string，非数组）
  - ✅ 字段名翻译：username→用户名、password→密码、email→邮箱等
  - ✅ 错误类型翻译：missing→不能为空、string_too_short→长度不能少于N个字符等
  - ✅ 多条错误分号分隔

## 任务 2：test_register.py 断言更新 `✅ 已完成`

- 文件：`xlfoundryTest/auth-center/tests/test_register.py`
- 改动：T16-T18 从检查英文数组改为检查中文字符串
- acceptance_criteria:
  - ✅ T16 断言包含"密码"+"不能少于"
  - ✅ T17 断言包含"用户名"+"不能少于"
  - ✅ T18 断言包含"邮箱"+"不能为空"

## 任务 3：test_validation.py 新建 `✅ 已完成`

- 文件：`xlfoundryTest/auth-center/tests/test_validation.py`
- 改动：4 个独立测试覆盖全局 handler
- acceptance_criteria:
  - ✅ 密码太短 → 422 + 中文
  - ✅ 用户名太短 → 422 + 中文
  - ✅ 缺少必填字段 → 422 + 中文
  - ✅ 多个错误 → 分号分隔

## 任务 4：部署验证 `✅ 已完成`

- 线上部署通过，健康检查通过

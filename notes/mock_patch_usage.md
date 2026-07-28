# Mock & Patch 使用笔记

> pytest 单元测试中 Mock 外部依赖的完整参考

---

## 核心概念

| 概念 | 一句话 | Java 对照 |
|------|--------|-----------|
| **Mock** | 假对象本身，所有属性和方法都自动生成 | Mockito 的 `@Mock` |
| **patch** | 把目标对象替换成 Mock 的工具 | Mockito 的 `@InjectMocks` + `when().thenReturn()` |

---

## patch 路径规则

**黄金法则**：patch 的路径是"被测函数内部使用的模块路径"，不是原始定义路径。

```python
# ❌ 错误 — patch 原始定义处
@patch("langchain_openai.ChatOpenAI")

# ✅ 正确 — patch 被测函数所在模块里的引用
@patch("src.utils.llm_retry.ChatOpenAI")
```

### 多个 patch 参数顺序（容易搞反）

```python
# 装饰器从下往上执行，参数从外往里传入
# 离函数最近的 patch，在参数列表里排第一个

@patch("src.utils.llm_retry.time.sleep")   # ← 外层
@patch("src.utils.llm_retry.ChatOpenAI")   # ← 内层
def test_xxx(mock_chat_openai, mock_sleep):  # 内层的先入参
    ...
```

---

## Mock 作为类使用（ChatOpenAI 场景）

当 Mock 被当作类调用时，`return_value` 代表"实例"：

```python
mock_chat_openai.return_value        # ← ChatOpenAI() 返回什么？这个假实例
mock_llm_instance = mock_chat_openai.return_value
mock_llm_instance.invoke.return_value = fake_response  # ← 假实例.invoke() 返回什么
```

调用链拆解：

```
ChatOpenAI(...)                           # 调用 mock_chat_openai
  → 返回 mock_chat_openai.return_value    # 即"假实例"
    → 假实例.invoke(messages)             # 调用 invoke
      → 返回 invoke.return_value          # 即 fake_response
```

---

## Mock 完整 API

### 设定行为

| 属性 | 作用 | 示例 |
|------|------|------|
| `return_value` | 每次调用都返回同一个值 | `mock.invoke.return_value = fake` |
| `side_effect` | 异常 / 列表（依次返回）/ 函数 | `mock.invoke.side_effect = [resp1, resp2]` |

`return_value` 和 `side_effect` 互斥，设了后者前者失效。

### 检查调用历史

| 属性/方法 | 作用 |
|-----------|------|
| `called` | 是否被调用过（bool） |
| `call_count` | 被调了几次（int） |
| `call_args` | **最后一次**调用的参数 |
| `call_args_list` | **所有**调用的参数列表 |
| `assert_called_once()` | 断言只被调了一次 |
| `assert_called_once_with(...)` | 断言只调了一次且参数匹配 |
| `assert_called_with(...)` | 断言最后一次调用参数匹配 |
| `assert_any_call(...)` | 断言任意一次调用参数匹配 |
| `assert_not_called()` | 断言从未被调用 |
| `reset_mock()` | 清空所有调用记录 |

### 特殊参数

| 参数 | 作用 |
|------|------|
| `spec=ClassName` | 限制 Mock 只能访问真实类存在的属性/方法，访问不存在的会抛 `AttributeError` |

---

## 常用模式

### 模式 1：构造假 LLM 响应

```python
def make_fake_response(content: str, finish_reason: str = "stop"):
    fake = Mock()
    fake.content = content
    fake.content.strip.return_value = content
    fake.response_metadata = {"finish_reason": finish_reason}
    return fake
```

### 模式 2：多次调用返回不同值

```python
mock_llm.invoke.side_effect = [
    fake_fail_response,   # 第一次 → 非法 JSON（触发重试）
    fake_ok_response,     # 第二次 → 合法 JSON
]
```

### 模式 3：验证方法调用次数

```python
assert mock_llm.invoke.call_count == 2
mock_sleep.assert_called_once_with(2)   # 验证参数也匹配
mock_sleep.assert_not_called()
```

### 模式 4：验证指数退避

```python
assert mock_sleep.call_args_list == [
    ((2,), {}),   # 第一次重试前等 2 秒
    ((4,), {}),   # 第二次重试前等 4 秒
]
```

### 模式 5：Mock 内部的子函数

```python
@patch("src.utils.llm_retry.parse_llm_json")
def test_xxx(mock_parse):
    mock_parse.side_effect = [RuntimeError("炸"), {"status": "ok"}]
```

---

## Mock 自动生成链（陷阱）

未设置属性时，Mock 自动生成新的 Mock，永不报错：

```python
m = Mock()
print(m.anything.you.want.deep.chain())  # → 不会报错，返回一个 Mock
```

这意味着漏设返回值时测试**不会炸**，只是拿到空 Mock 继续跑——排查起来比较隐蔽。

---

## 关键对比

| 常规测试 | Mock 测试 |
|---------|----------|
| 验证"输出对不对" | 验证"走没走对分支" |
| 输入 → 断言输出 | 设定返回 → 调用 → 断言调用次数/参数 |
| 测数据转换 | 测代码逻辑流转 |
| 不需要 patch | 用 patch 替换外部依赖 |

---

## 实战备忘（本项目中的使用）

- `test_json_parser.py` — 无 Mock，纯函数单元测试
- `test_store.py` — 无 Mock，内存操作不依赖外部
- `test_models.py` — 无 Mock，Pydantic 校验是纯 Python
- `test_llm_retry.py` — Mock `ChatOpenAI` + `time.sleep`，验证重试/退避/温度逻辑

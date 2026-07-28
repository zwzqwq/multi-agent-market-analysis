# pytest fixture 使用笔记

## 什么是 fixture

fixture 是 pytest 的"测试数据工厂"——用 `@pytest.fixture` 标记的函数，返回值会被自动注入到同名参数的测试函数中。

## 基本用法

### 简单 fixture（每次创建新对象）

```python
@pytest.fixture
def store():
    return ReportStore()

def test_create_and_get(store):   # store 自动注入
    report_id = store.create("test")
    ...
```

等价于 JUnit 的 `@BeforeEach`：每个测试函数调用前都执行一次 fixture，拿到全新的对象。

### 生命周期控制

```python
@pytest.fixture(scope="function")   # 默认：每个测试函数一次
def store():
    return ReportStore()

@pytest.fixture(scope="module")     # 整个 .py 文件共享一个
def expensive_resource():
    return create_expensive_thing()

@pytest.fixture(scope="session")    # 整个测试运行只创建一次
def db_connection():
    return connect_to_db()
```

## fixture vs 普通函数

| 场景 | 用什么 |
|------|--------|
| 无参数的工具函数（如 make_fake_response） | 普通函数，放 conftest.py |
| 需要自动注入的测试准备（如 store） | `@pytest.fixture` |
| 有参数但想共享 | 普通函数 + import |

## conftest.py 的作用

- 放在 `tests/` 目录下
- 同目录及所有子目录的测试文件**自动**看到里面的内容
- 不需要 `import tests.conftest`
- fixture 自动注册，普通函数/类需要显式 import

"""
测试 call_llm_with_retry 函数

需要 Mock 的对象：
1. time.sleep → 避免测试等待
2. ChatOpenAI.invoke → 避免真实调用 LLM
"""
import pytest
from unittest.mock import patch, Mock
from src.utils.llm_retry import call_llm_with_retry
from tests.conftest import make_fake_response

# ============================================================
# 场景 1：第一次调用就成功
# ============================================================

@patch("src.utils.llm_retry.time.sleep")  # Mock sleep
@patch("src.utils.llm_retry.ChatOpenAI")  # Mock ChatOpenAI
def test_call_llm_success_first_try(mock_chat_openai, mock_sleep):
    """第一次调用就成功，不重试"""
    # 1. 配置 Mock 返回值
    # 不使用fixture的手动写法
    # mock_response = Mock()
    # mock_response.content = '{"status": "ok"}'
    # mock_response.response_metadata = {"finish_reason": "stop"}

    mock_response=make_fake_response(content='{"status": "ok"}')
    
    # ChatOpenAI().invoke() 返回 mock_response
    mock_llm_instance = mock_chat_openai.return_value
    mock_llm_instance.invoke.return_value = mock_response
    
    # 2. 调用被测函数
    messages = [{"role": "user", "content": "测试"}]
    result = call_llm_with_retry(messages, "test_node")
    
    # 3. 验证结果
    assert result == {"status": "ok"}
    
    # 4. 验证调用次数
    mock_chat_openai.assert_called_once()          # 创建了一次 ChatOpenAI
    mock_llm_instance.invoke.assert_called_once()  # 调用了一次 invoke
    mock_sleep.assert_not_called()                 # 没有调用 sleep（不需要重试）


# ============================================================
# 场景 2：失败一次后成功
# ============================================================

@patch("src.utils.llm_retry.time.sleep")
@patch("src.utils.llm_retry.ChatOpenAI")
def test_call_llm_retry_once_then_success(mock_chat_openai, mock_sleep):
    """第一次失败，第二次成功"""
    # 1. 配置 Mock：第一次抛异常，第二次返回成功
    # mock_response = Mock()
    # mock_response.content = '{"status": "ok"}'
    # mock_response.response_metadata = {"finish_reason": "stop"}
    
    mock_response=make_fake_response('{"status": "ok"}')
    
    mock_llm_instance = mock_chat_openai.return_value
    
    # 第一次调用失败（parse_llm_json 会抛出 RuntimeError）
    # 第二次调用成功
    mock_llm_instance.invoke.side_effect = [
        make_fake_response("invalid json"),
        mock_response
    ]
    
    # 2. 调用被测函数
    messages = [{"role": "user", "content": "测试"}]
    result = call_llm_with_retry(messages, "test_node")
    
    # 3. 验证结果
    assert result == {"status": "ok"}
    
    # 4. 验证调用次数
    assert mock_llm_instance.invoke.call_count == 2  # 调用了 2 次
    mock_sleep.assert_called_once_with(2)            # 等待了 2 秒（指数退避：2^1）


# ============================================================
# 场景 3：三次都失败，抛出异常
# ============================================================

@patch("src.utils.llm_retry.time.sleep")
@patch("src.utils.llm_retry.ChatOpenAI")
def test_call_llm_all_failures(mock_chat_openai, mock_sleep):
    """三次都失败，最终抛出异常"""
    # 1. 配置 Mock：每次都返回无效 JSON
    mock_llm_instance = mock_chat_openai.return_value
    mock_llm_instance.invoke.return_value = make_fake_response("invalid json")
    
    # 2. 调用被测函数，预期抛异常
    messages = [{"role": "user", "content": "测试"}]
    
    with pytest.raises(RuntimeError, match="3 次重试全部失败"):
        call_llm_with_retry(messages, "test_node")
    
    # 3. 验证调用次数
    assert mock_llm_instance.invoke.call_count == 3  # 调用了 3 次
    assert mock_sleep.call_count == 2                 # 等待了 2 次
    mock_sleep.assert_any_call(2)                     # 第一次等待 2 秒
    mock_sleep.assert_any_call(4)                     # 第二次等待 4 秒


# ============================================================
# 场景 4：指数退避时间验证（1s → 2s → 4s）
# ============================================================

@patch("src.utils.llm_retry.time.sleep")
@patch("src.utils.llm_retry.ChatOpenAI")
def test_exponential_backoff(mock_chat_openai, mock_sleep):
    """验证指数退避时间是否正确：2^1=2s, 2^2=4s"""
    # 1. 配置 Mock：每次都失败
    mock_llm_instance = mock_chat_openai.return_value
    mock_llm_instance.invoke.return_value = make_fake_response("invalid json")
    
    # 2. 调用被测函数
    messages = [{"role": "user", "content": "测试"}]
    
    with pytest.raises(RuntimeError):
        call_llm_with_retry(messages, "test_node")
    
    # 3. 验证退避时间
    # 第1次失败后等待 2^1 = 2 秒
    # 第2次失败后等待 2^2 = 4 秒
    assert mock_sleep.call_args_list == [
        ((2,), {}),   # 第一次重试前等待 2 秒
        ((4,), {})    # 第二次重试前等待 4 秒
    ]


# ============================================================
# 场景 5：temperature 参数随重试次数递增
# ============================================================

@patch("src.utils.llm_retry.time.sleep")
@patch("src.utils.llm_retry.ChatOpenAI")
def test_temperature_increases(mock_chat_openai, mock_sleep):
    """验证 temperature 参数：0.0 → 0.3 → 0.6"""
    # 1. 配置 Mock：每次都失败
    mock_llm_instance = mock_chat_openai.return_value
    mock_llm_instance.invoke.return_value = make_fake_response("invalid json")
    
    # 2. 调用被测函数
    messages = [{"role": "user", "content": "测试"}]
    
    with pytest.raises(RuntimeError):
        call_llm_with_retry(messages, "test_node")
    
    # 3. 验证 ChatOpenAI 初始化时的 temperature 参数
    # 第1次: temperature = 0.3 * 0 = 0.0
    # 第2次: temperature = 0.3 * 1 = 0.3
    # 第3次: temperature = 0.3 * 2 = 0.6
    calls = mock_chat_openai.call_args_list
    
    assert calls[0].kwargs.get('temperature') == 0.0  # 第一次
    assert calls[1].kwargs.get('temperature') == 0.3  # 第二次
    assert calls[2].kwargs.get('temperature') == 0.6  # 第三次


# ============================================================
# 场景 6：Mock parse_llm_json 而不是 LLM
# ============================================================

@patch("src.utils.llm_retry.parse_llm_json")
@patch("src.utils.llm_retry.time.sleep")
@patch("src.utils.llm_retry.ChatOpenAI")
def test_mock_parse_llm_json(mock_chat_openai, mock_sleep, mock_parse):
    """Mock parse_llm_json，测试重试逻辑"""
    # 1. 配置 Mock：第一次失败，第二次成功
    mock_parse.side_effect = [
        RuntimeError("解析失败"),
        {"status": "ok"}
    ]
    
    # 2. 调用被测函数
    messages = [{"role": "user", "content": "测试"}]
    result = call_llm_with_retry(messages, "test_node")
    
    # 3. 验证结果
    assert result == {"status": "ok"}
    assert mock_parse.call_count == 2  # 调用了 2 次
    mock_sleep.assert_called_once()    # 等待了 1 次

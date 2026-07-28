from unittest.mock import Mock


def make_fake_response(content: str, finish_reason: str = "stop"):
    """构造一个假的 ChatOpenAI invoke() 返回值"""
    fake = Mock()
    fake.content = content
    fake.response_metadata = {"finish_reason": finish_reason}
    return fake
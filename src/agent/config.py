from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass(frozen=True)
class AgentConfig:
    enabled: bool = False
    base_url: str = 'http://127.0.0.1:3080/aurabot/api/ext/bjgbot'
    token: str = field(default='', repr=False)

    @classmethod
    def load(cls, value):
        if not isinstance(value, dict):
            raise ValueError('agent 必须是 JSON 对象')
        if value.keys() - {'enabled', 'base_url', 'token'}:
            raise ValueError('agent 包含未知配置字段')
        config = cls(**value)
        if type(config.enabled) is not bool or not isinstance(config.token, str):
            raise ValueError('agent.enabled 必须是布尔值，token 必须是字符串')
        if not isinstance(config.base_url, str):
            raise ValueError('agent.base_url 必须是字符串')
        url = urlparse(config.base_url)
        if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('agent.base_url 必须是本机 HTTP 地址')
        if config.enabled and not config.token:
            raise ValueError('启用 agent 时必须配置 token')
        return config

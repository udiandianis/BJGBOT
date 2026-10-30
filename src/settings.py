import json
from datetime import time
from dataclasses import dataclass, field
from functools import lru_cache
from .paths import CONFIG_PATH
from .agent.config import AgentConfig

CONFIG_LAYOUT = {
    'bot': {'qq': 'bot_qq', 'host': 'host', 'port': 'port', 'request_timeout': 'request_timeout'},
    'napcat': {'api_url': 'napcat_url', 'api_token': 'napcat_token', 'webui_port': 'napcat_webui_port',
               'windows_launcher': 'napcat_windows_launcher', 'linux_qq_path': 'napcat_linux_qq_path'},
    'welcome': {'groups': 'welcome_groups', 'message': 'welcome_message'},
    'ai': {
        'request_timeout': 'ai_request_timeout',
        'chatgpt': {'base_url': 'gpt_base_url', 'model': 'gpt_model', 'api_key': 'gpt_api_key'},
        'deepseek': {'base_url': 'deepseek_base_url', 'model': 'deepseek_model', 'api_key': 'deepseek_api_key'},
    },
    'platforms': {'luogu': {'cookies': 'luogu_cookies', 'training_max_year_gap': 'training_max_year_gap'}},
    'collections': {
        'admins': 'media_admins',
        'r2': {'endpoint': 'r2_endpoint', 'bucket': 'r2_bucket', 'access_key_id': 'r2_access_key_id',
               'secret_access_key': 'r2_secret_access_key', 'url_expiry_seconds': 'r2_url_expiry_seconds'},
    },
    'problemset': {'refresh_time': 'problemset_refresh_time'},
}


@lru_cache(maxsize=1)
def get_settings():
    """复用启动时读取的配置，修改 JSON 后需重启服务。"""
    return Settings.load()


@dataclass(frozen=True)
class Settings:
    bot_qq: int
    host: str
    port: int
    napcat_url: str
    napcat_token: str = field(repr=False)
    request_timeout: float
    ai_request_timeout: float
    welcome_groups: tuple[int, ...]
    media_admins: tuple[int, ...]
    gpt_base_url: str
    gpt_model: str
    gpt_api_key: str = field(repr=False)
    deepseek_base_url: str
    deepseek_model: str
    deepseek_api_key: str = field(repr=False)
    luogu_cookies: dict = field(repr=False)
    training_max_year_gap: int | None
    napcat_windows_launcher: str
    napcat_linux_qq_path: str
    napcat_webui_port: int
    welcome_message: str
    problemset_refresh_time: str
    r2_endpoint: str
    r2_bucket: str
    r2_access_key_id: str = field(repr=False)
    r2_secret_access_key: str = field(repr=False)
    r2_url_expiry_seconds: int
    agent: AgentConfig = field(default_factory=AgentConfig)
    login_page: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls):
        """读取并校验 bot_settings.json；缺失或无效配置抛出 ValueError。"""
        path = CONFIG_PATH
        if not path.exists():
            raise ValueError('缺少 bot_settings.json，请在 config 目录填写项目配置')
        document = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(document, dict):
            raise ValueError('bot_settings.json 必须是 JSON 对象')
        agent = AgentConfig.load(document.pop('agent', {}))
        login_page = document.pop('login_page', {})
        if not isinstance(login_page, dict) or set(login_page) - {'password_hash', 'session_secret', 'qr_path', 'host', 'port', 'secure_cookie', 'require_password'}:
            raise ValueError('login_page 配置字段不合法')
        if any(not isinstance(value, str) for key, value in login_page.items() if key not in ('port', 'secure_cookie', 'require_password')):
            raise ValueError('login_page 的密码、会话密钥、路径和监听地址必须使用字符串')
        if type(login_page.get('port', 5011)) is not int or not 1 <= login_page.get('port', 5011) <= 65535:
            raise ValueError('login_page.port 必须是有效端口号')
        for key in ('secure_cookie', 'require_password'):
            if type(login_page.get(key, True)) is not bool:
                raise ValueError(f'login_page.{key} 必须为布尔值')
        data = {}

        def read_section(section, layout, location):
            """校验每层配置字段，并提取供服务使用的值。"""
            if not isinstance(section, dict):
                raise ValueError(f'{location} 必须是 JSON 对象')
            missing, unknown = layout.keys() - section.keys(), section.keys() - layout.keys()
            if missing or unknown:
                raise ValueError(f'{location} 配置字段不匹配：缺少 {sorted(missing)}，未知 {sorted(unknown)}')
            for key, target in layout.items():
                if isinstance(target, dict):
                    read_section(section[key], target, f'{location}.{key}')
                else:
                    data[target] = section[key]

        read_section(document, CONFIG_LAYOUT, 'bot_settings.json')
        for key in ('bot_qq', 'port', 'napcat_webui_port', 'r2_url_expiry_seconds'):
            if type(data[key]) is not int:
                raise ValueError(f'{key} 必须是整数')
        if data['bot_qq'] <= 0 or not all(1 <= data[key] <= 65535 for key in ('port', 'napcat_webui_port')):
            raise ValueError('QQ 号或端口不合法')
        for key in ('request_timeout', 'ai_request_timeout'):
            if type(data[key]) not in (int, float) or not 0 < data[key] < float('inf'):
                raise ValueError(f'{key} 必须是有限正数')
        for key in ('welcome_groups', 'media_admins'):
            if not isinstance(data[key], list) or any(type(value) is not int or value <= 0 for value in data[key]):
                raise ValueError(f'{key} 必须是正整数数组')
            data[key] = tuple(data[key])
        if not isinstance(data['luogu_cookies'], dict):
            raise ValueError('luogu_cookies 必须是 JSON 对象')
        if data['training_max_year_gap'] is not None and (type(data['training_max_year_gap']) is not int or data['training_max_year_gap'] < 0):
            raise ValueError('training_max_year_gap 必须是非负整数或 null')
        for key in ('host', 'napcat_url', 'napcat_token', 'gpt_base_url', 'gpt_model', 'gpt_api_key',
                    'deepseek_base_url', 'deepseek_model', 'deepseek_api_key',
                    'napcat_windows_launcher', 'napcat_linux_qq_path', 'welcome_message', 'problemset_refresh_time',
                    'r2_endpoint', 'r2_bucket', 'r2_access_key_id', 'r2_secret_access_key'):
            if not isinstance(data[key], str):
                raise ValueError(f'{key} 必须是字符串')
        if not 60 <= data['r2_url_expiry_seconds'] <= 604800:
            raise ValueError('r2_url_expiry_seconds 必须在 60 到 604800 之间')
        if not all(data[key].strip() for key in (
                'r2_endpoint', 'r2_bucket', 'r2_access_key_id', 'r2_secret_access_key')):
            raise ValueError('请完整填写 R2 连接配置')
        try:
            time.fromisoformat(data['problemset_refresh_time'])
            if len(data['problemset_refresh_time']) != 5:
                raise ValueError
        except ValueError:
            raise ValueError('problemset_refresh_time 必须为 HH:MM 格式的有效时间') from None
        return cls(**data, agent=agent, login_page=login_page)

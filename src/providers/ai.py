import html
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def deepseek_balance(settings):
    """查询当前 DeepSeek 账号余额，保留币种和赠金、充值余额明细。"""
    if not settings.deepseek_api_key:
        raise ValueError('DS 尚未配置 API Key')
    base_url = settings.deepseek_base_url.rstrip('/')
    if base_url.endswith('/v1'):
        base_url = base_url[:-3]
    response = requests.get(base_url + '/user/balance',
                            headers={'Authorization': 'Bearer ' + settings.deepseek_api_key}, timeout=5)
    response.raise_for_status()
    result = response.json()
    balances = result.get('balance_infos')
    if not isinstance(balances, list) or not balances:
        raise ValueError('当前 DS 服务未返回余额信息')
    fields = ('currency', 'total_balance', 'granted_balance', 'topped_up_balance')
    if any(not isinstance(row, dict) or any(not isinstance(row.get(field), str) for field in fields) for row in balances):
        raise ValueError('DS 余额数据格式不正确')
    return {'available': result.get('is_available') is True,
            'balances': [{field: row[field] for field in fields} for row in balances]}


def answer(question, settings, provider):
    """使用 GPT 或 DeepSeek 的独立配置回答，未配置密钥时返回提示。"""
    if provider not in ('gpt', 'deepseek'):
        raise ValueError('未知 AI 服务')
    api_key = getattr(settings, provider + '_api_key')
    if not api_key:
        return 'AI 服务尚未配置 API Key'
    url = getattr(settings, provider + '_base_url').rstrip('/') + '/chat/completions'
    with requests.Session() as session:
        retry = Retry(total=1, backoff_factor=0.5, allowed_methods={'POST'},
                      status_forcelist=(408, 409, 429, 500, 502, 503, 504), raise_on_status=False)
        session.mount('https://', HTTPAdapter(max_retries=retry))
        session.mount('http://', HTTPAdapter(max_retries=retry))
        response = session.post(url, headers={'Authorization': f'Bearer {api_key}'},
            json={'model': getattr(settings, provider + '_model'),
                  'messages': [{'role': 'user', 'content': html.unescape(question) + '切记需要中文回答'}]},
            timeout=settings.request_timeout)
        response.raise_for_status()
        result = response.json()
    choices = result.get('choices') or []
    if not choices:
        return 'AI 未返回内容'
    return choices[0]['message'].get('content') or 'AI 未返回内容'

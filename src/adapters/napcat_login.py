"""通过本机 WebUI 的登录接口更新二维码，不重启 QQ 进程。"""
import hashlib
import json
import time
from pathlib import Path

import requests

from .napcat import NapCatError


def refresh_expired_qr(settings):
    """二维码临近过期时更新；已扫码、已登录或重连期间保持原状态。"""
    location = settings.login_page.get('qr_path')
    if not location:
        return False
    qr_path = Path(location)
    if qr_path.exists() and 0 <= time.time() - qr_path.stat().st_mtime < 100:
        return False
    config_path = qr_path.parent.parent / 'config' / 'webui.json'
    token = json.loads(config_path.read_text(encoding='utf-8-sig')).get('token')
    if not isinstance(token, str) or not token:
        raise ValueError('NapCat WebUI 未配置登录令牌')
    base = f'http://127.0.0.1:{settings.napcat_webui_port}/api'
    with requests.Session() as session:
        def call(path, payload=None, timeout=5):
            """仅调用固定的本机登录接口，不向页面返回管理凭据。"""
            response = session.post(base + path, json=payload or {}, timeout=timeout)
            response.raise_for_status()
            result = response.json()
            if result.get('code') != 0:
                raise NapCatError('NapCat 二维码接口请求失败')
            return result.get('data') or {}

        credential = call('/auth/login', {'hash': hashlib.sha256((token + '.napcat').encode()).hexdigest()}).get('Credential')
        if not credential:
            raise NapCatError('NapCat WebUI 登录失败')
        session.headers['Authorization'] = 'Bearer ' + credential
        status = call('/QQLogin/CheckLoginStatus')
        if status.get('isLogin') or status.get('qrLoginAccepted') or status.get('loginPhase') in (
                'qrcode_scanned', 'initializing', 'reconnecting'):
            return False
        result = call('/QQLogin/RefreshQRcode', timeout=15)
        return bool(result.get('qrcodeurl'))

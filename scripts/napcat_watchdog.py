"""由 systemd 定时检查 QQ 登录状态，掉线后有限度地重启 NapCat。"""
import json
import logging
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import requests

from src.adapters.napcat import NapCatClient, NapCatError
from src.adapters.napcat_login import refresh_expired_qr
from src.settings import get_settings

logger = logging.getLogger(__name__)
STATE_PATH = Path('/var/lib/napcat-watchdog/state.json')


def check_login(settings, state_path=STATE_PATH):
    """连续三次离线后重启一次，恢复在线后才允许下一轮自动恢复。"""
    if subprocess.run(['systemctl', 'is-active', '--quiet', 'napcat.service'], check=False).returncode:
        logger.info('NapCat 未运行，跳过登录检查，保留手动停止状态')
        return
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {
        'failures': 0, 'last_restart': 0, 'attempted_restart': False,
    }
    try:
        status = NapCatClient(replace(settings, request_timeout=5)).call('get_status')
        online = isinstance(status, dict) and status.get('online') is True
    except (requests.RequestException, NapCatError, ValueError) as error:
        logger.warning('QQ 状态接口不可用：%s', type(error).__name__)
        online = False
    now = time.time()
    restart = False
    if online:
        if state['failures']:
            logger.info('QQ 已恢复在线，重新允许掉线自动恢复')
        state.update(failures=0, attempted_restart=False)
    else:
        state['failures'] = min(3, state['failures'] + 1)
        if state['attempted_restart']:
            try:
                if refresh_expired_qr(settings):
                    logger.info('已更新待扫码二维码，无需重启 NapCat')
            except (requests.RequestException, NapCatError, ValueError, OSError) as error:
                logger.warning('更新待扫码二维码失败：%s', type(error).__name__)
        elif state['failures'] >= 3 and now - state['last_restart'] >= 600:
            state.update(last_restart=now, attempted_restart=True)
            restart = True
        else:
            logger.warning('QQ 离线检查：%s/3，重启最短间隔为十分钟', state['failures'])
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state), encoding='utf-8')
    temporary.replace(state_path)
    if restart:
        logger.warning('QQ 连续三次离线，自动重启 NapCat 尝试重新登录')
        subprocess.run(['systemctl', 'restart', 'napcat.service'], check=True, timeout=45)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    check_login(get_settings())

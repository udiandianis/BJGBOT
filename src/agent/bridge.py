"""事件分流及管理员群开关；人格、记忆、压缩由 DSH + Aurabot 社区本体处理。"""
import logging
import re
import requests

logger = logging.getLogger(__name__)


class AgentBridge:
    def __init__(self, settings, client):
        self.settings, self.client = settings, client
        self.config = settings.agent

    def request(self, path, body):
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(self.config.base_url.rstrip('/') + path, json=body,
                                    headers={'Authorization': 'Bearer ' + self.config.token}, timeout=(2, 8))
            response.raise_for_status()
            result = response.json()
        if result.get('ok') is not True:
            raise RuntimeError('Agent 接口未接受请求')
        return result

    def control(self, event):
        match = re.fullmatch(r'#AGENT\s+(START|END)', event.text, re.I)
        if not match:
            return None
        if not self.settings.media_admins or event.user_id != self.settings.media_admins[0]:
            return '仅机器人管理员可以操作 AGENT。'
        if not self.config.enabled:
            return 'Agent 服务尚未启用。'
        try:
            result = self.request('/control', {'action': match[1].upper(), 'group_id': event.group_id,
                                               'user_id': event.user_id, 'message_id': event.message_id})
            return '本群 Agent 已' + ('开启，可以 @我或叫“大肥鱼”聊天。' if result['enabled'] else '关闭，原有指令仍可正常使用。')
        except Exception as error:
            logger.error('Agent control failed: %s', type(error).__name__)
            return 'Agent 服务暂时不可用，群开关未确认生效，请稍后重试。'

    def forward(self, data):
        if not self.config.enabled or data.get('user_id') == self.settings.bot_qq:
            return
        if data.get('message_type') not in ('group', 'private') and data.get('notice_type') != 'notify':
            return
        try:
            self.request('/event', {'event': data})
        except Exception as error:
            logger.error('Agent event forwarding failed: %s', type(error).__name__)

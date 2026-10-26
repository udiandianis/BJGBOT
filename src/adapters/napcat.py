import requests
from ..events import segments


class NapCatError(RuntimeError):
    pass


class NapCatClient:
    def __init__(self, settings):
        """保存 NapCat 连接配置。"""
        self.settings = settings

    def call(self, action, **params):
        """调用 OneBot API，返回 data；HTTP 或协议错误抛出异常。"""
        headers = {}
        if self.settings.napcat_token:
            headers['Authorization'] = 'Bearer ' + self.settings.napcat_token
        response = requests.post(self.settings.napcat_url.rstrip('/') + '/' + action,
                                 json=params, headers=headers, timeout=self.settings.request_timeout)
        response.raise_for_status()
        result = response.json()
        if result.get('retcode') != 0:
            raise NapCatError(f'{action}: {result.get("message") or result.get("wording")}')
        return result.get('data')

    def send_group(self, group_id, message):
        """向指定群发送消息，返回 NapCat 接口结果。"""
        if isinstance(message, str) and '[CQ:' in message:
            message = segments(message)
        return self.call('send_group_msg', group_id=group_id, message=message)

    def send_forward(self, group_id, text):
        """按段落拆分文本，以多节点合并转发消息发送到指定群。"""
        nodes = [{'type': 'node', 'data': {'name': 'BJGBOT', 'uin': str(self.settings.bot_qq),
                  'content': [{'type': 'text', 'data': {'text': paragraph}}]}}
                 for paragraph in text.split('\n\n') if paragraph.strip()]
        return self.call('send_group_forward_msg', group_id=group_id, messages=nodes)

    def get_message(self, message_id):
        """按消息 ID 查询原消息，供回复收藏使用。"""
        return self.call('get_msg', message_id=message_id)

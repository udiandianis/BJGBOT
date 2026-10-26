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
        if isinstance(message, list):
            message = [dict(part, data=dict(part['data'])) for part in message]
            for part in message:
                if part['type'] not in ('image', 'video', 'record', 'file'):
                    continue
                data = part['data']
                location = data.get('url') or data.get('file', '')
                if not location.startswith(('https://', 'http://')):
                    continue
                data['file'] = self.download_file(location)
                data.pop('url', None)
        return self.call('send_group_msg', group_id=group_id, message=message)

    def download_file(self, url):
        """通过独立下载接口取得 NapCat 本机路径，网络异常最多重试两次。"""
        for attempt in range(3):
            try:
                result = self.call('download_file', url=url, thread_count=1)
                if not result or not result.get('file'):
                    raise NapCatError('下载接口未返回文件路径')
                return result['file']
            except (requests.RequestException, NapCatError):
                if attempt == 2:
                    raise

    def send_forward(self, group_id, text):
        """按段落拆分文本，以多节点合并转发消息发送到指定群。"""
        nodes = [{'type': 'node', 'data': {'name': 'BJGBOT', 'uin': str(self.settings.bot_qq),
                  'content': [{'type': 'text', 'data': {'text': paragraph}}]}}
                 for paragraph in text.split('\n\n') if paragraph.strip()]
        return self.call('send_group_forward_msg', group_id=group_id, messages=nodes)

    def get_message(self, message_id):
        """按消息 ID 查询原消息，供回复收藏使用。"""
        return self.call('get_msg', message_id=message_id)

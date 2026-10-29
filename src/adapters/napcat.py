import requests
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from ..events import segments

MEDIA_DOWNLOAD_SLOTS = threading.BoundedSemaphore(2)


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
        if not isinstance(message, list):
            return self.call('send_group_msg', group_id=group_id, message=message)
        message = [dict(part, data=dict(part['data'])) for part in message]
        remote = [part['data'] for part in message if part['type'] in ('image', 'video', 'record', 'file')
                  and (part['data'].get('url') or part['data'].get('file', '')).startswith(('https://', 'http://'))]
        if not remote:
            return self.call('send_group_msg', group_id=group_id, message=message)
        with MEDIA_DOWNLOAD_SLOTS, TemporaryDirectory(prefix='bjgbot-send-') as directory:
            for index, data in enumerate(remote):
                location = data.get('url') or data['file']
                path = Path(directory) / (str(index) + Path(urlsplit(location).path).suffix)
                self.download_file(location, path)
                data['file'] = str(path)
                data.pop('url', None)
            return self.call('send_group_msg', group_id=group_id, message=message)

    def download_file(self, url, path):
        """流式下载到本次发送的临时文件，网络异常最多重试两次。"""
        for attempt in range(3):
            try:
                with requests.get(url, stream=True, timeout=self.settings.request_timeout) as response:
                    response.raise_for_status()
                    with path.open('wb') as output:
                        for chunk in response.iter_content(1024 * 1024):
                            output.write(chunk)
                return
            except requests.RequestException:
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

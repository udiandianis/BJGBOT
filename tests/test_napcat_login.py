import json
import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from src.adapters.napcat_login import refresh_expired_qr
from src.adapters.napcat import NapCatError
from tests.support import test_settings


class NapCatLoginTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / 'cache').mkdir()
        (root / 'config').mkdir()
        self.qr = root / 'cache' / 'qrcode.png'
        self.qr.write_bytes(b'qr')
        os.utime(self.qr, (time.time() - 180, time.time() - 180))
        (root / 'config' / 'webui.json').write_text(json.dumps({'token': 'test-token'}))
        self.settings = replace(test_settings(), login_page={'qr_path': str(self.qr)})

    def responses(self, status=None, result=None):
        values = [{'Credential': 'test-credential'}, status or {'loginPhase': 'waiting_qrcode'},
                  result or {'qrcodeurl': 'test-qr-url'}]
        return [Mock(json=lambda value=value: {'code': 0, 'data': value}) for value in values]

    def test_expired_qr_uses_native_refresh_without_restart(self):
        with patch('src.adapters.napcat_login.requests.Session') as factory:
            session = factory.return_value.__enter__.return_value
            session.headers = {}
            session.post.side_effect = self.responses()
            self.assertTrue(refresh_expired_qr(self.settings))
        self.assertTrue(session.post.call_args.args[0].endswith('/QQLogin/RefreshQRcode'))
        self.assertEqual(session.headers['Authorization'], 'Bearer test-credential')

    def test_fresh_qr_is_not_replaced(self):
        os.utime(self.qr, None)
        with patch('src.adapters.napcat_login.requests.Session') as factory:
            self.assertFalse(refresh_expired_qr(self.settings))
        factory.assert_not_called()

    def test_scanned_or_online_qr_is_not_replaced(self):
        for status in ({'isLogin': True}, {'qrLoginAccepted': True}, {'loginPhase': 'qrcode_scanned'},
                       {'loginPhase': 'initializing'}, {'loginPhase': 'reconnecting'}):
            with self.subTest(status=status), patch('src.adapters.napcat_login.requests.Session') as factory:
                session = factory.return_value.__enter__.return_value
                session.post.side_effect = self.responses(status)
                self.assertFalse(refresh_expired_qr(self.settings))
                self.assertEqual(session.post.call_count, 2)

    def test_webui_errors_are_not_reported_as_success(self):
        with patch('src.adapters.napcat_login.requests.Session') as factory:
            factory.return_value.__enter__.return_value.post.return_value = Mock(json=lambda: {'code': -1})
            with self.assertRaises(NapCatError):
                refresh_expired_qr(self.settings)

    def test_no_login_page_config_does_not_touch_webui(self):
        with patch('src.adapters.napcat_login.requests.Session') as factory:
            self.assertFalse(refresh_expired_qr(test_settings()))
        factory.assert_not_called()

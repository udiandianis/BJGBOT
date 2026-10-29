import os
import re
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from werkzeug.security import generate_password_hash

from src.providers.ai import deepseek_balance
from src.web.login import create_login_app
from src.storage import users
from tests.support import test_settings


class LoginPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = generate_password_hash('test-password')

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.qr = Path(directory.name) / 'qrcode.png'
        database = patch.object(users, 'DB_PATH', Path(directory.name) / 'bot.db')
        database.start()
        self.addCleanup(database.stop)
        self.qr.write_bytes(b'test-image')
        self.settings = replace(test_settings(), login_page={'password_hash': self.password_hash,
            'session_secret': 'test-secret-' * 5, 'qr_path': str(self.qr)})
        self.napcat = Mock()
        self.napcat.call.return_value = {'online': False}
        self.app = create_login_app(self.settings, self.napcat)
        self.client = self.app.test_client()

    def request(self, path='/', method='GET', **kwargs):
        return self.client.open(path, method=method, base_url='https://localhost', **kwargs)

    def csrf(self):
        return re.search(rb'name="csrf-token" content="([^"]+)"', self.request().data)[1].decode()

    def login(self):
        return self.request(method='POST', data={'csrf': self.csrf(), 'password': 'test-password'})

    def test_private_endpoints_require_login_and_do_not_query_providers(self):
        for path in ('/status', '/qrcode.png', '/balance', '/balance-history'):
            response = self.request(path)
            self.assertEqual(response.status_code, 401)
            self.assertNotIn(b'test-image', response.data)
        self.napcat.call.assert_not_called()

    def test_login_cookie_and_csrf(self):
        self.assertEqual(self.request(method='POST', data={'password': 'test-password'}).status_code, 403)
        response = self.login()
        self.assertEqual(response.status_code, 302)
        cookie = response.headers['Set-Cookie']
        for attribute in ('Secure', 'HttpOnly', 'SameSite=Strict'):
            self.assertIn(attribute, cookie)
        self.assertEqual(self.request('/refresh', method='POST').status_code, 403)

    def test_failed_password_attempts_are_limited(self):
        token = self.csrf()
        for _ in range(5):
            self.assertEqual(self.request(method='POST', data={'csrf': token, 'password': 'wrong'}).status_code, 401)
        self.assertEqual(self.request(method='POST', data={'csrf': token, 'password': 'wrong'}).status_code, 429)

    def test_explicit_http_mode_supports_login_and_protected_status(self):
        settings = replace(self.settings, login_page={**self.settings.login_page, 'secure_cookie': False})
        client = create_login_app(settings, self.napcat).test_client()
        page = client.get('/', base_url='http://localhost')
        token = re.search(rb'name="csrf-token" content="([^"]+)"', page.data)[1].decode()
        response = client.post('/', base_url='http://localhost', data={'csrf': token, 'password': 'test-password'})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('Secure;', response.headers['Set-Cookie'])
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        self.assertEqual(client.get('/status', base_url='http://localhost').status_code, 200)

    def test_public_mode_does_not_require_password_but_disallows_restart(self):
        settings = replace(self.settings, login_page={**self.settings.login_page, 'require_password': False,
                                                     'secure_cookie': False, 'password_hash': ''})
        client = create_login_app(settings, self.napcat).test_client()
        page = client.get('/')
        self.assertNotIn(b'type="password"', page.data)
        self.assertEqual(client.get('/status').status_code, 200)
        self.assertFalse(client.get('/status').json['can_refresh'])
        image = client.get('/qrcode.png')
        self.assertEqual(image.data, b'test-image')
        image.close()
        with patch('src.web.login.deepseek_balance', return_value={'available': True, 'balances': []}):
            self.assertEqual(client.get('/balance').status_code, 200)
        with patch('src.web.login.subprocess.run') as restart:
            self.assertEqual(client.post('/refresh').status_code, 403)
        restart.assert_not_called()

    def test_fresh_qr_can_be_downloaded_and_is_not_cached(self):
        self.login()
        self.assertTrue(self.request('/status').json['qr_available'])
        response = self.request('/qrcode.png?download=1')
        self.assertEqual(response.data, b'test-image')
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        response.close()

    def test_expired_and_missing_qr_are_not_shown(self):
        self.login()
        os.utime(self.qr, (time.time() - 180, time.time() - 180))
        self.assertFalse(self.request('/status').json['qr_available'])
        self.assertEqual(self.request('/qrcode.png').status_code, 410)
        self.qr.unlink()
        self.assertEqual(self.request('/qrcode.png').status_code, 404)

    def test_online_does_not_return_qr_or_restart_qq(self):
        self.login()
        self.napcat.call.return_value = {'online': True}
        with patch('src.web.login.subprocess.run') as restart:
            self.assertTrue(self.request('/status').json['online'])
            self.assertEqual(self.request('/qrcode.png').status_code, 409)
            self.assertEqual(self.request('/refresh', method='POST', headers={'X-CSRF-Token': self.csrf()}).status_code, 409)
        restart.assert_not_called()

    def test_refresh_requires_auth_and_is_rate_limited(self):
        self.login()
        token = self.csrf()
        with patch('src.web.login.subprocess.run') as restart:
            self.assertEqual(self.request('/refresh', method='POST', headers={'X-CSRF-Token': token}).status_code, 200)
            self.assertEqual(self.request('/refresh', method='POST', headers={'X-CSRF-Token': token}).status_code, 429)
        restart.assert_called_once_with(['systemctl', 'restart', 'napcat.service'], check=True, timeout=45)
        self.assertFalse(self.request('/status').json['qr_available'])

    def test_balance_is_authenticated_and_cached_without_exposing_key(self):
        self.login()
        result = {'available': True, 'balances': [{'currency': 'CNY', 'total_balance': '12.34',
                   'granted_balance': '0.00', 'topped_up_balance': '12.34'}]}
        with patch('src.web.login.deepseek_balance', return_value=result) as fetch:
            first = self.request('/balance')
            self.assertEqual(first.json['balances'][0]['total_balance'], '12.34')
            self.request('/balance')
        fetch.assert_called_once()
        self.assertNotIn(b'api_key', first.data)

    def test_balance_failure_does_not_become_zero(self):
        self.login()
        with patch('src.web.login.deepseek_balance', side_effect=ValueError('unavailable')):
            response = self.request('/balance')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('balances', response.json)

    def test_balance_records_history_and_limits_query_range(self):
        self.login()
        result = {'available': True, 'balances': [{'currency': 'CNY', 'total_balance': '12.34',
                  'granted_balance': '0.00', 'topped_up_balance': '12.34'}]}
        with patch('src.web.login.deepseek_balance', return_value=result):
            self.assertEqual(self.request('/balance').status_code, 200)
        history = self.request('/balance-history?days=7&currency=CNY')
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json['samples'], 1)
        self.assertEqual(history.json['points'][0]['balance'], '12.34')
        for days in ('1', '14', '45', '180'):
            self.assertEqual(self.request('/balance-history?days=' + days).status_code, 200)
        for days in ('0', '181', '999', '-1', '7.5', 'abc', '9' * 5000):
            self.assertEqual(self.request('/balance-history?days=' + days).status_code, 400)
        self.assertEqual(self.request('/balance-history?currency=invalid').status_code, 400)

    def test_status_requests_share_short_cache_and_then_refresh(self):
        self.login()
        with patch('src.web.login.time.monotonic', return_value=100) as clock:
            self.assertFalse(self.request('/status').json['online'])
            self.napcat.call.return_value = {'online': True}
            self.assertFalse(self.request('/status').json['online'])
            self.napcat.call.assert_called_once_with('get_status')
            clock.return_value = 104
            self.assertTrue(self.request('/status').json['online'])
        self.assertEqual(self.napcat.call.call_count, 2)

    def test_logout_does_not_logout_qq(self):
        self.login()
        self.request('/logout', method='POST', data={'csrf': self.csrf()})
        self.assertEqual(self.request('/status').status_code, 401)
        self.napcat.call.assert_not_called()

    def test_separate_app_does_not_expose_bot_or_napcat_admin(self):
        self.login()
        for path in ('/agent/commands', '/health', '/webui', '/get_status'):
            self.assertEqual(self.request(path).status_code, 404)


class DeepSeekBalanceTests(unittest.TestCase):
    def test_balance_uses_configured_key_and_strips_v1(self):
        settings = replace(test_settings(), deepseek_api_key='test-key', deepseek_base_url='https://api.deepseek.com/v1/')
        result = {'is_available': True, 'balance_infos': [{'currency': 'CNY', 'total_balance': '1.00',
                  'granted_balance': '0.00', 'topped_up_balance': '1.00', 'extra': 'ignored'}]}
        with patch('src.providers.ai.requests.get', return_value=Mock(json=lambda: result)) as get:
            balance = deepseek_balance(settings)
        get.assert_called_once_with('https://api.deepseek.com/user/balance', headers={'Authorization': 'Bearer test-key'}, timeout=5)
        self.assertEqual(balance['balances'][0]['total_balance'], '1.00')
        self.assertNotIn('extra', balance['balances'][0])

    def test_unsupported_balance_response_is_not_zero(self):
        with patch('src.providers.ai.requests.get', return_value=Mock(json=lambda: {})):
            with self.assertRaises(ValueError):
                deepseek_balance(test_settings())

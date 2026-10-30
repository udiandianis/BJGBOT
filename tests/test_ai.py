import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
import requests
from src.providers.ai import answer


class AIRequestTests(unittest.TestCase):
    def setUp(self):
        self.statuses = [200]
        self.calls = []
        test = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                test.calls.append((self.path, self.headers['Authorization'], body))
                self.send_response(test.statuses.pop(0))
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'choices': [{'message': {'content': '回答'}}]}).encode())

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.settings = SimpleNamespace(gpt_api_key='test', gpt_model='test-model',
            gpt_base_url=f'http://127.0.0.1:{self.server.server_port}/v1/', request_timeout=2, ai_request_timeout=5)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_transient_failure_retries_with_same_request(self):
        self.statuses = [503, 200]
        self.assertEqual(answer('A&amp;B', self.settings, 'gpt'), '回答')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0], self.calls[1])
        path, authorization, body = self.calls[0]
        self.assertEqual(path, '/v1/chat/completions')
        self.assertEqual(authorization, 'Bearer test')
        self.assertEqual(body['messages'][0]['content'], 'A&B切记需要中文回答')

    def test_permission_error_is_not_retried(self):
        self.statuses = [401]
        with self.assertRaises(requests.HTTPError):
            answer('你好', self.settings, 'gpt')
        self.assertEqual(len(self.calls), 1)

    def test_retries_are_limited_to_one(self):
        self.statuses = [503, 503]
        with self.assertRaises(requests.HTTPError):
            answer('你好', self.settings, 'gpt')
        self.assertEqual(len(self.calls), 2)

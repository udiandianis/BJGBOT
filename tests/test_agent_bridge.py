import unittest
from dataclasses import replace
from unittest.mock import Mock, patch
import requests
from src.agent.bridge import AgentBridge
from src.agent.config import AgentConfig
from src.app import create_app
from src.events import GroupMessage
from tests.support import test_settings
from tests.test_bot import group_event


class AgentBridgeTests(unittest.TestCase):
    def setUp(self):
        self.settings = replace(test_settings(), media_admins=(10001,),
                                agent=AgentConfig(enabled=True, token='test-agent-token'))
        self.client = Mock()
        self.bridge = AgentBridge(self.settings, self.client)

    def event(self, text, **kwargs):
        return GroupMessage.parse(group_event(text, **kwargs))

    def test_group_owner_and_admin_are_not_robot_admin(self):
        with patch.object(self.bridge, 'request') as request:
            for role in ('member', 'admin', 'owner'):
                self.assertIn('仅机器人管理员', self.bridge.control(self.event('#AGENT START', role=role)))
                self.assertIn('仅机器人管理员', self.bridge.control(self.event('#AGENT END', role=role)))
            request.assert_not_called()

    def test_owner_controls_the_current_group_only(self):
        with patch.object(self.bridge, 'request', return_value={'ok': True, 'enabled': True}) as request:
            self.assertIn('已开启', self.bridge.control(self.event('#agent start', user_id=10001)))
            self.assertEqual(request.call_args.args[1]['group_id'], 7)
            self.assertEqual(request.call_args.args[1]['user_id'], 10001)
        with patch.object(self.bridge, 'request', return_value={'ok': True, 'enabled': False}):
            self.assertIn('已关闭', self.bridge.control(self.event('#AGENT END', user_id=10001)))

    def test_failed_control_does_not_claim_success(self):
        with patch.object(self.bridge, 'request', side_effect=requests.ConnectionError), self.assertLogs('src.agent.bridge'):
            self.assertIn('未确认生效', self.bridge.control(self.event('#AGENT END', user_id=10001)))

    def test_owner_comes_from_configuration(self):
        bridge = AgentBridge(replace(self.settings, media_admins=(42,)), self.client)
        with patch.object(bridge, 'request', return_value={'ok': True, 'enabled': True}):
            self.assertIn('已开启', bridge.control(self.event('#AGENT START', user_id=42)))
            self.assertIn('仅机器人管理员', bridge.control(self.event('#AGENT START', user_id=10001)))

    def test_disabled_agent_never_calls_sidecar(self):
        bridge = AgentBridge(replace(self.settings, agent=AgentConfig()), self.client)
        with patch.object(bridge, 'request') as request:
            bridge.forward(group_event('大肥鱼你好'))
            self.assertIn('尚未启用', bridge.control(self.event('#AGENT START', user_id=10001)))
            request.assert_not_called()

    def test_bridge_authentication_and_timeout(self):
        with patch('src.agent.bridge.requests.Session') as factory:
            session = factory.return_value.__enter__.return_value
            session.post.return_value.json.return_value = {'ok': True}
            self.bridge.request('/event', {'event': {}})
            request = session.post.call_args
            self.assertTrue(request.args[0].endswith('/ext/bjgbot/event'))
            self.assertEqual(request.kwargs['headers'], {'Authorization': 'Bearer test-agent-token'})
            self.assertEqual(request.kwargs['timeout'], (2, 8))

    def test_original_commands_do_not_also_trigger_agent(self):
        services, agent = Mock(), Mock()
        agent.control.return_value = None
        services.answer.return_value = '旧模型回答'
        app = create_app(self.settings, self.client, services, agent)
        client = app.test_client()
        client.post('/', json=group_event('#DS 原有问题'))
        services.answer.assert_called_once_with('deepseek', '原有问题')
        agent.forward.assert_not_called()
        client.post('/', json=group_event('大肥鱼你好'))
        agent.forward.assert_called_once()

    def test_group_control_does_not_call_legacy_services_or_model(self):
        services = Mock()
        with patch.object(self.bridge, 'request', return_value={'ok': True, 'enabled': True}):
            app = create_app(self.settings, self.client, services, self.bridge)
            app.test_client().post('/', json=group_event('#AGENT START', user_id=10001))
        services.answer.assert_not_called()
        self.client.send_group.assert_called_once()
        self.assertIn('本群 Agent 已开启', self.client.send_group.call_args.args[1])

    def test_private_and_poke_events_are_forwarded(self):
        agent = Mock()
        app = create_app(self.settings, self.client, Mock(), agent)
        for event in ({'message_type': 'private', 'user_id': 42, 'message': 'hi'},
                      {'notice_type': 'notify', 'sub_type': 'poke', 'group_id': 7, 'user_id': 42}):
            app.test_client().post('/', json=event)
        self.assertEqual(agent.forward.call_count, 2)

    def test_command_descriptions_require_token_and_never_expose_secrets(self):
        client = create_app(self.settings, self.client, Mock()).test_client()
        self.assertEqual(client.get('/agent/commands').status_code, 401)
        response = client.get('/agent/commands', headers={'Authorization': 'Bearer test-agent-token'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('#bind', response.get_json()['commands'])
        self.assertNotIn('test-agent-token', response.get_data(as_text=True))

    def test_config_accepts_legacy_and_refuses_remote_sidecar(self):
        self.assertFalse(AgentConfig.load({}).enabled)
        with self.assertRaises(ValueError):
            AgentConfig.load({'enabled': True})
        with self.assertRaises(ValueError):
            AgentConfig.load({'base_url': 'http://example.com/agent'})
        self.assertNotIn('hidden-token', repr(AgentConfig(token='hidden-token')))

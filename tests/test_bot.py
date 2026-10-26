import sqlite3
import json
import os
import tempfile
import unittest
import requests
import sys
from dataclasses import replace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import Mock, patch
from src.app import create_app
from src.settings import Settings
from tests.support import test_settings
from src import settings as settings_module
from src.storage import users
from src.services import accounts, practice, statistics, trainings
from src.services.duels import DuelService
from src.providers import codeforces, luogu, chaoxing, atcoder, contests, ai
from src.adapters.napcat import NapCatClient


def group_event(text, mentions=(), reply_id=None, role='member', user_id=42):
    message = [{'type': 'at', 'data': {'qq': str(mentioned)}} for mentioned in mentions]
    message.append({'type': 'text', 'data': {'text': text}})
    if reply_id is not None:
        message.insert(0, {'type': 'reply', 'data': {'id': str(reply_id)}})
    return {'message_type': 'group', 'group_id': 7, 'user_id': user_id, 'message_id': 99,
            'sender': {'user_id': user_id, 'role': role, 'nickname': 'Tester'}, 'message': message}


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.services, self.napcat = Mock(), Mock()
        self.services.query.return_value = 'query result'
        self.services.bind.return_value = '绑定成功'
        self.services.statistics.return_value = 'chart'
        self.app = create_app(test_settings(), self.napcat, self.services)
        self.client = self.app.test_client()

    def post(self, event):
        return self.client.post('/', json=event)

    def test_webhook_returns_json_without_quick_operations(self):
        events = ({}, group_event('#help'), group_event('hello'),
                  group_event('#help', user_id=3661517915),
                  {'notice_type': 'group_increase', 'group_id': 8, 'user_id': 42},
                  {'notice_type': 'group_increase', 'group_id': 7, 'user_id': 'bad'})
        for event in events:
            with self.subTest(event=event):
                response = self.post(event)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.is_json)
                self.assertEqual(response.get_json(), {})

    def test_help_matches_behavior(self):
        self.post(group_event('#help'))
        text = self.napcat.send_forward.call_args.args[1]
        for description in ('#duel reset', '已绑定姓名和班级且今日有提交', '#bind name', '来只关键词'):
            self.assertIn(description, text)
        for removed in ('set1', '素材'):
            self.assertNotIn(removed, text)

    def test_empty_unknown_and_self_messages(self):
        for event in ({}, group_event('hello'), dict(group_event(''), message=[]), group_event('#help', user_id=3661517915), dict(group_event('#help'), sender='bad')):
            self.assertEqual(self.post(event).status_code, 200)
        self.napcat.send_group.assert_not_called()

    def test_report_progress_is_sent_before_query(self):
        for command, method in (('做题汇总', self.services.statistics), ('洛谷题单', self.services.training_report)):
            with self.subTest(command=command):
                self.napcat.reset_mock()
                def query(*args):
                    self.assertEqual(args, (7,))
                    self.assertEqual(self.napcat.send_group.call_count, 1)
                    self.assertIn('正在查询', self.napcat.send_group.call_args.args[1])
                    return 'report image'
                method.side_effect = query
                self.post(group_event(command, mentions=(test_settings().bot_qq,)))
                self.assertEqual(self.napcat.send_group.call_count, 2)
                self.assertEqual(self.napcat.send_group.call_args.args, (7, 'report image'))
                self.napcat.reset_mock()
                self.post(group_event(command))
                self.napcat.send_group.assert_not_called()

    def test_progress_failure_does_not_cancel_report(self):
        self.napcat.send_group.side_effect = [RuntimeError('network'), {}]
        with self.assertLogs('src.app', level='ERROR'):
            self.post(group_event('做题汇总', mentions=(test_settings().bot_qq,)))
        self.services.statistics.assert_called_once()
        self.assertEqual(self.napcat.send_group.call_args.args, (7, 'chart'))
        self.napcat.send_forward.assert_not_called()

    def test_invalid_json(self):
        self.assertEqual(self.post([]).status_code, 400)

    def test_welcome_mentions_member_with_separate_message_segment(self):
        settings = replace(test_settings(), welcome_groups=(7,), welcome_message='欢迎加入')
        client = create_app(settings, self.napcat, self.services).test_client()
        client.post('/', json={'notice_type': 'group_increase', 'group_id': 7, 'user_id': 42})
        self.napcat.send_group.assert_called_once_with(7, [
            {'type': 'at', 'data': {'qq': '42'}},
            {'type': 'text', 'data': {'text': '欢迎加入'}},
        ])

    def test_welcome_ignores_other_groups_and_invalid_notices(self):
        settings = replace(test_settings(), welcome_groups=(7,))
        client = create_app(settings, self.napcat, self.services).test_client()
        for notice in ({'group_id': 8, 'user_id': 42}, {'group_id': 7, 'user_id': 'bad'}):
            client.post('/', json={'notice_type': 'group_increase', **notice})
        self.napcat.send_group.assert_not_called()

    def test_daily_problem_feature_removed(self):
        self.post(group_event('每日题目', (3661517915,)))
        self.services.daily_problem.assert_not_called()
        self.assertNotIn('每日题目', self.app.extensions['bot_router'].help_text())

    def test_split_text_and_reply(self):
        event = group_event('')
        event['message'] = [{'type': 'text', 'data': {'text': '#codeforces '}}, {'type': 'text', 'data': {'text': 'tourist'}}]
        self.post(event)
        self.services.query.assert_called_once_with('codeforces', 'tourist')
        self.post(group_event('添加猫', (3661517915,), reply_id=10))
        self.services.media.add.assert_called_once_with('猫', 10)

    def test_delete_by_identifier_requires_bot_mention_but_not_reply(self):
        self.post(group_event('删除bjg-12'))
        self.services.media.request_delete.assert_not_called()
        self.post(group_event('删除bjg-12', (3661517915,)))
        self.services.media.request_delete.assert_called_once()
        self.assertEqual(self.services.media.request_delete.call_args.args[0], 'bjg-12')
        self.assertEqual(self.services.media.request_delete.call_args.args[1].user_id, 42)

    def test_cq_string_and_binding_fields(self):
        self.post(dict(group_event(''), message='[CQ:at,qq=3661517915] 签到'))
        self.services.checkin.assert_called_once()
        self.post(group_event('#bind name Alice'))
        self.services.bind.assert_called_once_with('name', 'Alice', 42)
        self.post(group_event('#bind codeforces tourist'))
        self.assertEqual(self.services.bind.call_args.args, ('codeforces_handle', 'tourist', 42))

    def test_all_full_binding_names(self):
        for account_type, field in users.BINDING_FIELDS.items():
            value = 'account password' if account_type == 'chaoxing' else 'account'
            self.post(group_event(f'#bind {account_type} {value}'))
            self.assertEqual(self.services.bind.call_args.args, (field, value, 42))

    def test_mentioned_platform_query(self):
        for platform in ('codeforces', 'nowcoder', 'luogu', 'atcoder'):
            self.post(group_event(platform, (11,)))
            self.assertEqual(self.services.query_bound.call_args.args, (11, users.BINDING_FIELDS[platform]))
        self.services.query_bound.reset_mock()
        self.post(group_event('codeforces'))
        self.post(group_event('codeforces', (11, 12)))
        self.services.query_bound.assert_not_called()

    def test_query_bound_and_media_forward(self):
        self.post(group_event('#nowcoder', (11,)))
        self.services.query_bound.assert_called_once_with(11, 'nowcoder_handle')
        self.services.media.list.return_value = 'keywords'
        self.post(group_event('给我看看'))
        self.assertEqual(self.napcat.send_forward.call_args.args, (7, 'keywords'))

    def test_slash_commands_removed(self):
        for command in ('/help', '/ask question', '/duel reset'):
            self.post(group_event(command))
        self.napcat.send_group.assert_not_called()
        self.napcat.send_forward.assert_not_called()

    def test_gpt_and_deepseek_commands(self):
        self.post(group_event('#GPT 你好'))
        self.services.answer.assert_called_with('gpt', '你好')
        self.post(group_event('#DS 你好'))
        self.services.answer.assert_called_with('deepseek', '你好')
        self.services.answer.reset_mock()
        self.post(group_event('#ask 你好'))
        self.post(group_event('#GPT'))
        self.post(group_event('#DS'))
        self.services.answer.assert_not_called()

    def test_removed_chart_and_remaining_table(self):
        for command in ('做题图表', '做题汇总2'):
            self.post(group_event(command, (3661517915,), role='admin'))
        self.services.statistics.assert_not_called()
        self.napcat.send_group.assert_not_called()
        self.post(group_event('做题汇总', (3661517915,)))
        self.services.statistics.assert_called_once_with(7)

    def test_duel_validation_and_reset(self):
        self.post(group_event('#duel 850', (11,)))
        self.services.invite.assert_not_called()
        self.post(group_event('#duel 800', (11,)))
        self.services.invite.assert_called_once_with(7, 42, 11, 800)
        self.post(group_event('#duel reset'))
        self.services.duel.assert_called_once_with(7, 'reset', 42)

    def test_exception_handling(self):
        self.services.contests.side_effect = RuntimeError('upstream unavailable')
        with self.assertLogs('src.app', level='ERROR'):
            self.assertEqual(self.post(group_event('#近期比赛')).status_code, 200)
        self.assertEqual(self.napcat.send_group.call_args.args[1], '处理失败，请稍后重试')


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.database_patch = patch.object(users, 'DB_PATH', self.root / 'bot.db')
        self.database_patch.start()
        users.init_db()

    def tearDown(self):
        self.database_patch.stop()
        self.directory.cleanup()

    def participants(self):
        users.update_user_fields(1, name='Alice', codeforces_handle='alice')
        users.update_user_fields(2, name='Bob', codeforces_handle='bob')
        return DuelService()

    def test_chaoxing_binding_is_json(self):
        accounts.bind('chaoxing_credentials', '测试账号 test-password', 1)
        self.assertEqual(json.loads(users.get_user_field(1, 'chaoxing_credentials')),
                         ['测试账号', 'test-password'])

    def test_initialization_preserves_user_data(self):
        users.update_user_fields(1, name='Alice', bot_rating=123, codeforces_handle='alice')
        users.init_db()
        users.init_db()
        self.assertEqual(users.get_user(1)['bot_rating'], 123)
        self.assertEqual(users.get_user(1)['codeforces_handle'], 'alice')

    def test_persistent_invitation_and_guards(self):
        service = self.participants()
        self.assertIn('发起', service.invite(7, 1, 2, 800))
        service = DuelService()
        self.assertIn('尚未接受', service.execute(7, 'judge', 2))
        self.assertIn('只有被挑战者', service.execute(7, 'accept', 1))
        self.assertIn('没有正在', service.execute(8, 'reject', 2))
        self.assertIn('已取消', service.execute(7, 'reset', 1))
        self.assertIn('发起', service.invite(7, 1, 2, 800))
        self.assertIn('拒绝', service.execute(7, 'reject', 2))
        self.assertEqual(service.execute(7, 'reset', 1), '重置成功')

    def test_network_failure_preserves_active_state(self):
        service = self.participants()
        service.invite(7, 1, 2, 800)
        with patch.object(practice, 'select_problem', return_value=(100, 'A')):
            service.execute(7, 'accept', 2)
        with patch.object(practice, 'accepted_submission', side_effect=RuntimeError('timeout')):
            with self.assertRaises(RuntimeError):
                service.execute(7, 'judge', 1)
        self.assertEqual(users.get_user(1)['duel_available'], 0)
        with patch.object(practice, 'accepted_submission', return_value=None):
            self.assertIn('无人完成', service.execute(7, 'judge', 1))
        self.assertEqual(users.get_user(1)['duel_available'], 1)

    def test_duel_scores_update_once(self):
        service = self.participants()
        service.invite(7, 1, 2, 800)
        with patch.object(practice, 'select_problem', return_value=(100, 'A')), patch('src.services.duels.time.time', return_value=100):
            service.execute(7, 'accept', 2)
        with patch.object(practice, 'accepted_submission', side_effect=[{'creationTimeSeconds': 160}, None]):
            self.assertIn('alice 获胜', service.execute(7, 'judge', 1))
        rating = users.get_user(1)['bot_rating']
        self.assertGreater(rating, 0)
        self.assertEqual(rating, -users.get_user(2)['bot_rating'])
        service.execute(7, 'judge', 1)
        self.assertEqual(users.get_user(1)['bot_rating'], rating)

    def test_challenger_loses_and_tied_finish(self):
        for finish_times in ([None, {'creationTimeSeconds': 160}], [{'creationTimeSeconds': 160}, {'creationTimeSeconds': 160}]):
            service = self.participants()
            service.invite(7, 1, 2, 800)
            with patch.object(practice, 'select_problem', return_value=(100, 'A')), patch('src.services.duels.time.time', return_value=100):
                service.execute(7, 'accept', 2)
            with patch.object(practice, 'accepted_submission', side_effect=finish_times):
                result = service.execute(7, 'judge', 2)
            self.assertIn('bob 获胜' if finish_times[0] is None else '双方同时完成', result)
            self.assertEqual(users.get_user(1)['duel_available'], 1)
            self.assertEqual(users.get_user(2)['duel_available'], 1)

    def test_restarted_active_duel_and_cross_group(self):
        service = self.participants()
        service.invite(7, 1, 2, 800)
        with patch.object(practice, 'select_problem', return_value=(100, 'A')):
            service.execute(7, 'accept', 2)
        service = DuelService()
        self.assertIn('没有正在', service.execute(8, 'judge', 1))
        self.assertIn('没有正在', service.execute(7, 'judge', 3))
        users.update_user_fields(1, bot_rating=123)
        users.update_user_fields(2, bot_rating=456)
        self.assertIn('已取消', service.execute(8, 'reset', 1))
        self.assertEqual(users.get_user(1)['duel_available'], 1)
        self.assertEqual(users.get_user(2)['duel_available'], 1)
        self.assertEqual(users.get_user(1)['bot_rating'], 123)
        self.assertEqual(users.get_user(2)['bot_rating'], 456)
        self.assertIn('没有正在', service.execute(7, 'judge', 1))
        self.assertIn('发起', service.invite(7, 1, 2, 800))

    def test_reset_preserves_unrelated_active_duel(self):
        service = self.participants()
        users.update_user_fields(3, codeforces_handle='charlie', duel_available=0)
        with users.connect() as connection:
            connection.execute('INSERT INTO duels (group_id,challenger,challenged,rating,status) VALUES (7,1,2,800,\'pending\')')
            connection.execute('INSERT INTO duels (group_id,challenger,challenged,rating,status) VALUES (8,2,3,800,\'active\')')
            connection.execute('UPDATE users SET duel_available=0 WHERE qq_id=2')
        self.assertIn('已取消', service.execute(7, 'reset', 1))
        self.assertEqual(users.get_user(1)['duel_available'], 1)
        self.assertEqual(users.get_user(2)['duel_available'], 0)
        self.assertEqual(users.get_user(3)['duel_available'], 0)
        with users.connect() as connection:
            self.assertEqual(connection.execute('SELECT group_id FROM duels').fetchone()['group_id'], 8)

    def test_random_problem_settles_once(self):
        self.participants()
        users.update_user_fields(1, assigned_problem='[100, "A"]', assigned_at=100)
        with patch.object(practice, 'accepted_submission', return_value={'creationTimeSeconds': 160, 'problem': {'rating': 800}}):
            self.assertIn('恭喜', practice.judge_problem(1))
            rating = users.get_user(1)['bot_rating']
            self.assertIn('暂无题目', practice.judge_problem(1))
            self.assertEqual(users.get_user(1)['bot_rating'], rating)

    def test_random_problem_skips_ac_but_allows_failed_attempt(self):
        self.participants()
        with users.connect() as connection:
            connection.executemany('INSERT INTO codeforces_problems VALUES (?, ?, ?)', [(100, 'A', 800), (100, 'B', 800)])
        history = [{'verdict': 'OK', 'problem': {'contestId': 100, 'index': 'A'}},
                   {'verdict': 'WRONG_ANSWER', 'problem': {'contestId': 100, 'index': 'B'}}]
        with patch.object(codeforces, 'api_result', return_value=[{'newRating': 850}]), patch.object(codeforces, 'fetch_submissions', return_value=history):
            self.assertIn('/100/B', practice.random_problem(1))
        self.assertEqual(json.loads(users.get_user(1)['assigned_problem']), [100, 'B'])

    def test_all_solved_or_query_failure_preserves_assignment(self):
        self.participants()
        with users.connect() as connection:
            connection.execute('INSERT INTO codeforces_problems VALUES (?, ?, ?)', (100, 'A', 800))
        users.update_user_fields(1, assigned_problem='[200, "A"]', assigned_at=100)
        history = [{'verdict': 'OK', 'problem': {'contestId': 100, 'index': 'A'}}]
        with patch.object(codeforces, 'api_result', return_value=[]), patch.object(codeforces, 'fetch_submissions', return_value=history):
            with self.assertRaisesRegex(ValueError, '已全部通过'):
                practice.random_problem(1)
        with patch.object(codeforces, 'api_result', side_effect=RuntimeError('timeout')):
            with self.assertRaises(RuntimeError):
                practice.random_problem(1)
        self.assertEqual(users.get_user(1)['assigned_problem'], '[200, "A"]')
        self.assertEqual(users.get_user(1)['assigned_at'], 100)


    def test_problemset_download_is_persisted_and_reused(self):
        response = Mock()
        response.json.return_value = {'status': 'OK', 'result': {'problems': [
            {'contestId': 100, 'index': 'A', 'rating': 800},
            {'contestId': 100, 'index': 'A', 'rating': 800},
            {'contestId': 101, 'index': 'B', 'rating': 900},
            {'contestId': 102, 'index': 'C'}]}}
        with patch.object(practice.http, 'get', return_value=response) as request:
            self.assertEqual(practice.select_problem(850), (100, 'A'))
            self.assertEqual(practice.select_problem(950), (101, 'B'))
            request.assert_called_once()
        with users.connect() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM codeforces_problems').fetchone()[0], 2)

    def test_problemset_failure_does_not_leave_partial_cache(self):
        response = Mock()
        with patch.object(practice.http, 'get', return_value=response):
            for payload, error in (({'status': 'FAILED'}, RuntimeError),
                                   ({'status': 'OK', 'result': {'problems': []}}, ValueError)):
                response.json.return_value = payload
                with self.assertRaises(error):
                    practice.refresh_problemset()
                with users.connect() as connection:
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM codeforces_problems').fetchone()[0], 0)

    def test_cached_problemset_never_requests_network(self):
        with users.connect() as connection:
            connection.execute('INSERT INTO codeforces_problems VALUES (?, ?, ?)', (100, 'A', 800))
        with patch.object(practice.http, 'get') as request:
            self.assertEqual(practice.select_problem(800), (100, 'A'))
            request.assert_not_called()


    def test_refresh_replaces_stale_problemset(self):
        with users.connect() as connection:
            connection.execute('INSERT INTO codeforces_problems VALUES (?, ?, ?)', (100, 'A', 800))
        response = Mock()
        response.json.return_value = {'status': 'OK', 'result': {'problems': [{'contestId': 101, 'index': 'B', 'rating': 900}]}}
        with patch.object(practice.http, 'get', return_value=response):
            self.assertEqual(practice.refresh_problemset(), 1)
        with users.connect() as connection:
            self.assertEqual([tuple(row) for row in connection.execute('SELECT * FROM codeforces_problems')], [(101, 'B', 900)])

    def test_refresh_rolls_back_write_failure(self):
        with users.connect() as connection:
            connection.execute('INSERT INTO codeforces_problems VALUES (?, ?, ?)', (100, 'A', 800))
        response = Mock()
        response.json.return_value = {'status': 'OK', 'result': {'problems': [{'contestId': 101, 'index': None, 'rating': 900}]}}
        with patch.object(practice.http, 'get', return_value=response), self.assertRaises(sqlite3.IntegrityError):
            practice.refresh_problemset()
        with users.connect() as connection:
            self.assertEqual([tuple(row) for row in connection.execute('SELECT * FROM codeforces_problems')], [(100, 'A', 800)])


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.config = json.loads((Path(__file__).resolve().parents[1] / 'config/bot_settings.example.json').read_text(encoding='utf-8'))
        self.config['bot']['qq'] = 123
        self.config['collections']['r2'].update(endpoint='https://example.invalid', bucket='test')
        self.config['ai']['chatgpt']['api_key'] = ''
        self.config['ai']['deepseek']['api_key'] = ''
        self.config['napcat']['api_token'] = ''
        self.config['platforms']['luogu']['cookies'] = {}
        self.config['collections']['r2']['access_key_id'] = 'test'
        self.config['collections']['r2']['secret_access_key'] = 'test'
        self.path = self.root / 'bot_settings.json'
        self.root_patch = patch.object(settings_module, 'CONFIG_PATH', self.path)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.directory.cleanup()

    def test_runtime_configuration_is_reused(self):
        settings_module.get_settings.cache_clear()
        try:
            with patch.object(Settings, 'load', return_value=test_settings()) as loader:
                self.assertIs(settings_module.get_settings(), settings_module.get_settings())
                loader.assert_called_once()
        finally:
            settings_module.get_settings.cache_clear()

    def test_configuration_from_json_only(self):
        self.config['bot'].update(qq=123, port=7777, request_timeout=4)
        self.config['welcome']['groups'] = [9]
        self.path.write_text(json.dumps(self.config), encoding='utf-8')
        with patch.dict(os.environ, BOT_QQ='999', BOT_PORT='8888'):
            settings = Settings.load()
        self.assertEqual((settings.bot_qq, settings.port, settings.request_timeout, settings.welcome_groups), (123, 7777, 4, (9,)))

    def test_missing_configuration_does_not_fall_back(self):
        with self.assertRaisesRegex(ValueError, '缺少 bot_settings.json'):
            Settings.load()
        self.config['bot'].pop('port')
        self.path.write_text(json.dumps(self.config), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'port'):
            Settings.load()

    def test_invalid_configuration(self):
        self.config['bot']['port'] = '5010'
        self.path.write_text(json.dumps(self.config), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'port 必须是整数'):
            Settings.load()

    def test_invalid_refresh_time(self):
        for value in ('24:00', '00:60', '0:00', '00:00:00', '12:30junk'):
            self.config['problemset']['refresh_time'] = value
            self.path.write_text(json.dumps(self.config), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'problemset_refresh_time'):
                Settings.load()

    def test_unknown_nested_field_is_rejected(self):
        self.config['collections']['r2']['unused'] = 'value'
        self.path.write_text(json.dumps(self.config), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'collections.r2.*unused'):
            Settings.load()

    def test_configuration_section_must_be_object(self):
        self.config['ai']['chatgpt'] = []
        self.path.write_text(json.dumps(self.config), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'ai.chatgpt 必须是 JSON 对象'):
            Settings.load()


class ProviderAndMediaTests(unittest.TestCase):
    def setUp(self):
        for module in (luogu, chaoxing, trainings, practice.http):
            configuration = patch.object(module, 'get_settings', return_value=test_settings())
            configuration.start()
            self.addCleanup(configuration.stop)
        self.database_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.database_directory.cleanup)
        database_patch = patch.object(users, 'DB_PATH', Path(self.database_directory.name) / 'bot.db')
        database_patch.start()
        self.addCleanup(database_patch.stop)
        users.init_db()

    def test_ai_services_use_separate_configuration(self):
        settings = replace(test_settings(), gpt_api_key='gpt-test', deepseek_api_key='ds-test')
        for provider in ('gpt', 'deepseek'):
            with patch.object(ai.requests, 'Session') as factory:
                session = factory.return_value.__enter__.return_value
                session.post.return_value.json.return_value = {'choices': [{'message': {'content': '回答'}}]}
                self.assertEqual(ai.answer('你好', settings, provider), '回答')
                request = session.post.call_args
                self.assertEqual(request.args[0], getattr(settings, provider + '_base_url').rstrip('/') + '/chat/completions')
                self.assertEqual(request.kwargs['headers']['Authorization'], 'Bearer ' + getattr(settings, provider + '_api_key'))
                self.assertEqual(request.kwargs['json']['model'], getattr(settings, provider + '_model'))
                self.assertEqual(request.kwargs['timeout'], settings.request_timeout)

    def test_codeforces_submission_pagination(self):
        first_page = [{'id': index} for index in range(10000)]
        with patch.object(codeforces, 'api_result', side_effect=[first_page, [{'id': 10000}]] ) as request, patch.object(codeforces.time, 'sleep'):
            self.assertEqual(len(codeforces.fetch_submissions('test')), 10001)
        self.assertEqual(request.call_args_list[1].kwargs['from'], 10001)

    def test_training_access_failure_is_not_zero(self):
        response = Mock(json=lambda: {'users': [{'uid': 1}]})
        session = Mock(headers={})
        session.get.return_value = response
        with patch.object(trainings, 'load_training_problems', return_value={100: {'P1'}}), patch.object(trainings.requests, 'Session') as factory, patch.object(trainings, 'page_data', side_effect=ValueError('Cookie expired')):
            factory.return_value.__enter__.return_value = session
            with self.assertRaisesRegex(ValueError, 'Cookie expired'):
                trainings.fetch_training_progress('test')

    def test_training_counts_have_meaningful_keys(self):
        session = Mock(headers={})
        session.get.return_value = Mock(json=lambda: {'users': [{'uid': 1}]})
        with patch.object(trainings, 'load_training_problems', return_value={100: {'P1', 'P2'}, 101: {'P1'}}), patch.object(trainings.requests, 'Session') as factory, patch.object(trainings, 'page_data', return_value={'passed':[{'pid':'P1'}]}):
            factory.return_value.__enter__.return_value = session
            self.assertEqual(trainings.fetch_training_progress('test'), {'by_training':{100:1, 101:1}, 'total':2})

    def test_forward_is_split_into_nodes(self):
        client = NapCatClient(test_settings())
        with patch.object(client, 'call') as call:
            client.send_forward(7, 'first\n\nsecond')
        nodes = call.call_args.kwargs['messages']
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[1]['data']['content'][0]['data']['text'], 'second')

    def test_signed_media_url_is_downloaded_and_temporary_file_is_removed(self):
        client = NapCatClient(test_settings())
        for kind in ('image', 'video', 'record', 'file'):
            response = Mock()
            response.iter_content.return_value = [b'image-data']
            with self.subTest(kind=kind), patch('src.adapters.napcat.requests.get') as download, patch.object(client, 'call') as api:
                download.return_value.__enter__.return_value = response
                def send(action, **params):
                    self.assertEqual(action, 'send_group_msg')
                    part = params['message'][0]
                    self.assertEqual(part['type'], kind)
                    self.assertEqual(Path(part['data']['file']).read_bytes(), b'image-data')
                api.side_effect = send
                client.send_group(7, f'[CQ:{kind},file=https://example.com/1.jpg?a=1&amp;b=x%2Fy&amp;c=3&#44;4]')
                download.assert_called_once_with('https://example.com/1.jpg?a=1&b=x%2Fy&c=3,4', stream=True, timeout=client.settings.request_timeout)
                self.assertFalse(Path(api.call_args.kwargs['message'][0]['data']['file']).exists())

    def test_media_download_retries_but_send_is_not_repeated(self):
        client = NapCatClient(test_settings())
        message = [{'type': 'image', 'data': {'url': 'https://example.com/image'}}]
        with patch('src.adapters.napcat.requests.get') as download, patch.object(client, 'call', return_value={'message_id': 1}) as api:
            response = download.return_value
            response.__enter__.return_value.iter_content.return_value = [b'image-data']
            download.side_effect = [requests.Timeout(), response]
            result = client.send_group(7, message)
        self.assertEqual(result, {'message_id': 1})
        self.assertEqual(download.call_count, 2)
        api.assert_called_once()
        self.assertNotIn('url', api.call_args.kwargs['message'][0]['data'])
        self.assertEqual(message[0]['data'], {'url': 'https://example.com/image'})

    def test_exhausted_download_does_not_send_media(self):
        client = NapCatClient(test_settings())
        with patch('src.adapters.napcat.requests.get', side_effect=requests.Timeout()) as download, patch.object(client, 'call') as api:
            with self.assertRaises(requests.Timeout):
                client.send_group(7, '[CQ:image,file=https://example.com/image]')
        self.assertEqual(download.call_count, 3)
        api.assert_not_called()

    def test_temporary_file_is_removed_when_send_fails(self):
        client = NapCatClient(test_settings())
        with patch('src.adapters.napcat.requests.get') as download, patch.object(client, 'call', side_effect=RuntimeError('send failed')) as api:
            download.return_value.__enter__.return_value.iter_content.return_value = [b'image-data']
            with self.assertRaises(RuntimeError):
                client.send_group(7, '[CQ:image,file=https://example.com/image]')
        self.assertFalse(Path(api.call_args.kwargs['message'][0]['data']['file']).exists())

    def test_plain_text_and_existing_segments_are_preserved(self):
        client = NapCatClient(test_settings())
        for message in ('hello &amp; world', [{'type': 'text', 'data': {'text': 'hello'}}]):
            with patch.object(client, 'call') as api:
                client.send_group(7, message)
                api.assert_called_once_with('send_group_msg', group_id=7, message=message)

    def test_luogu_cookie_sent_and_expiry_reported(self):
        settings = replace(test_settings(), luogu_cookies={'_uid': '123', '__client_id': 'test'})
        response = Mock(status_code=401)
        session = Mock()
        session.headers = {}
        session.get.side_effect = [Mock(json=lambda: {'users': [{'uid': 123, 'name': 'test'}]}), response]
        with patch.object(luogu, 'get_settings', return_value=settings), patch.object(luogu.requests, 'Session') as factory:
            factory.return_value.__enter__.return_value = session
            with self.assertRaisesRegex(ValueError, 'Cookie 已失效'):
                luogu.fetch_user_metrics('test')
        session.cookies.update.assert_called_once_with(settings.luogu_cookies)

    def test_chaoxing_invalid_binding(self):
        with patch.object(chaoxing.users, 'get_user_field', return_value='0'), patch.object(chaoxing.requests, 'Session') as session:
            self.assertIn('#bind chaoxing', chaoxing.fetch_pending_homework(1))
        session.assert_not_called()

    def test_atcoder_last_submission_and_real_ac_count(self):
        records = [{'epoch_second': timestamp, 'result': result, 'problem_id': 'abc_a', 'contest_id': 'abc'} for timestamp, result in [(100, 'AC'), (200, 'WA'), (300, 'AC')]]
        history = Mock(json=lambda: [{'IsRated': True, 'NewRating': 100}])
        with patch.object(atcoder, 'fetch_submissions', return_value=records), patch.object(atcoder, 'china_midnight', return_value=400), patch.object(atcoder.http, 'get', return_value=history):
            metrics = atcoder.fetch_user_metrics('test')
        self.assertEqual(metrics['accepted_submissions'], 2)
        self.assertEqual(metrics['today_submissions'], 0)
        self.assertEqual(metrics['attempts_for_latest_problem'], 3)
        self.assertTrue(metrics['latest_submission_accepted'])

    def test_first_ac_is_used(self):
        submissions = [{'verdict': 'OK', 'creationTimeSeconds': timestamp, 'problem': {'contestId': 100, 'index': 'A'}} for timestamp in (300, 200, 50)]
        with patch.object(codeforces, 'fetch_submissions', return_value=submissions):
            self.assertEqual(practice.accepted_submission('alice', 100, 'A', 100)['creationTimeSeconds'], 200)

    def test_empty_history_and_missing_verdict(self):
        with patch.object(codeforces, 'api_result', side_effect=[[], []]):
            self.assertEqual(codeforces.fetch_user_metrics('new')['total_submissions'], 0)
        submission = {'creationTimeSeconds': 100, 'problem': {'contestId': 100, 'index': 'A'}}
        with patch.object(codeforces, 'api_result', side_effect=[[], [submission]]):
            self.assertFalse(codeforces.fetch_user_metrics('new')['latest_submission_accepted'])

    def test_statistics_failure_is_not_zero(self):
        sample = [{'qq_id': 1, 'name': 'Alice', 'class_name': '计算机2302', 'codeforces_handle': 'alice', 'luogu_username': 'alice'}]
        def fetch(platform, provider, handle):
            if platform == 'CF':
                raise RuntimeError('timeout')
            return {'accepted': 0, 'submitted': 1}
        with patch.object(statistics.users, 'list_users', return_value=sample), patch.object(statistics, 'fetch_statistics', side_effect=fetch):
            records, _ = statistics.collect_statistics()
        self.assertIsNone(records[1]['platforms']['CF'])
        self.assertEqual(records[1]['rank'], '-')



if __name__ == '__main__':
    unittest.main()

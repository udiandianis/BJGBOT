import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from dataclasses import replace
from tests.support import test_settings

from src.services import accounts, trainings
from src.storage import users


class ClassBindingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        database = patch.object(users, 'DB_PATH', Path(self.directory.name) / 'bot.db')
        database.start()
        self.addCleanup(database.stop)
        users.init_db()

    def test_class_binding_and_rebinding(self):
        self.assertEqual(accounts.bind('class_name', '计算机2302', 1), '绑定成功')
        self.assertEqual(users.get_user(1)['enrollment_year'], 2023)
        self.assertEqual(accounts.bind('class_name', '软件2601', 1), '绑定成功')
        user = users.get_user(1)
        self.assertEqual((user['class_name'], user['enrollment_year']), ('软件2601', 2026))
        for invalid in ('计算机', '2302', '计算机202302', '计算机2a02'):
            self.assertIn('用法', accounts.bind('class_name', invalid, 1))
        self.assertEqual(users.get_user(1)['class_name'], '软件2601')

    def test_existing_user_survives_schema_upgrade(self):
        users.update_user_field(1, 'name', '测试用户')
        with users.connect() as connection:
            connection.execute('ALTER TABLE users DROP COLUMN class_name')
            connection.execute('ALTER TABLE users DROP COLUMN enrollment_year')
        users.init_db()
        self.assertEqual(users.get_user(1)['name'], '测试用户')
        self.assertIsNone(users.get_user(1)['enrollment_year'])

    def test_report_only_includes_recent_fully_bound_classes(self):
        for number, year in enumerate((2023, 2024, 2025, 2026, 2027), 1):
            users.update_user_fields(number, name=str(year), class_name=f'计算机{year % 100}02',
                                     enrollment_year=year, luogu_username=str(number))
        users.update_user_fields(6, name='未绑定班级', luogu_username='6')
        users.update_user_fields(7, class_name='计算机2602', enrollment_year=2026, luogu_username='7')
        users.update_user_fields(8, name='未绑定洛谷', class_name='计算机2602', enrollment_year=2026)
        with patch.object(trainings, 'datetime') as clock, \
             patch.object(trainings, 'get_settings', return_value=test_settings()) as settings, \
             patch.object(trainings, 'load_training_problems', return_value={100: {'P1'}}), \
             patch.object(trainings, 'fetch_user_progress', side_effect=lambda user, problems: {'name': user['name'], 'failed': True}) as fetch, \
             patch.object(trainings, 'configure_matplotlib'), \
             patch('matplotlib.pyplot.subplots', return_value=(Mock(), MagicMock())), \
             patch('matplotlib.pyplot.close'), \
             patch.object(trainings, 'REPORT_DIRECTORY', Path(self.directory.name)):
            clock.now.return_value.year = 2026
            trainings.get_png()
            self.assertEqual({call.args[0]['name'] for call in fetch.call_args_list}, {'2025', '2026'})
            fetch.reset_mock()
            clock.now.return_value.year = 2027
            trainings.get_png()
            self.assertEqual({call.args[0]['name'] for call in fetch.call_args_list}, {'2026', '2027'})
            settings.return_value = replace(test_settings(), training_max_year_gap=None)
            fetch.reset_mock()
            trainings.get_png()
            self.assertEqual({call.args[0]['name'] for call in fetch.call_args_list}, {'2023', '2024', '2025', '2026', '2027', '未绑定班级'})

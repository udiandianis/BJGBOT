import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.storage import balances, users
from tests.support import test_settings


class BalanceHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = patch.object(users, 'DB_PATH', Path(directory.name) / 'bot.db')
        database.start()
        self.addCleanup(database.stop)
        balances.init_storage()
        self.settings = replace(test_settings(), deepseek_api_key='history-test-key')
        self.start = int(datetime(2026, 10, 30, 12, tzinfo=balances.BEIJING_TIME).timestamp())

    def record(self, amount, timestamp, currency='CNY'):
        balances.record_balance(self.settings, {'balances': [{'currency': currency, 'total_balance': amount,
            'granted_balance': '0', 'topped_up_balance': amount}]}, timestamp)

    def history(self, **kwargs):
        return balances.balance_history(self.settings, now=self.start + 3600, **kwargs)

    def test_samples_survive_reinitialization_and_deduplicate_five_minute_bucket(self):
        self.record('10.00', self.start)
        self.record('9.99', self.start + 30)
        self.record('9.98', self.start + 300)
        balances.init_storage()
        result = self.history()
        self.assertEqual(result['samples'], 2)
        self.assertEqual(len(result['points']), 1)
        self.assertEqual(result['points'][0]['balance'], '9.98')
        self.assertEqual(result['points'][0]['date'], '2026-10-30')
        self.assertEqual(result['decrease'], '0.02')

    def test_decimal_changes_and_balance_increase_are_separate(self):
        self.record('1.000001', self.start)
        self.record('0.999999', self.start + 300)
        self.record('2.000001', self.start + 600)
        result = self.history()
        self.assertEqual(result['decrease'], '0.000002')
        self.assertEqual(result['increase'], '1.000002')
        self.assertEqual(result['daily'][0]['ending_balance'], '2.000001')
        self.assertEqual(result['points'][0]['balance'], '2.000001')

    def test_today_uses_beijing_midnight_and_previous_balance(self):
        midnight = int(datetime(2026, 10, 30, tzinfo=balances.BEIJING_TIME).timestamp())
        self.record('10.00', midnight - 300)
        self.record('9.90', midnight + 300)
        result = self.history(days=1)
        self.assertEqual(result['samples'], 1)
        self.assertEqual(result['daily'][0]['date'], '2026-10-30')
        self.assertEqual(result['decrease'], '0.10')

    def test_chart_has_one_latest_balance_per_beijing_day(self):
        self.record('10.00', self.start - 86400)
        self.record('9.00', self.start)
        self.record('8.50', self.start + 300)
        result = self.history()
        self.assertEqual([point['date'] for point in result['points']], ['2026-10-29', '2026-10-30'])
        self.assertEqual([point['balance'] for point in result['points']], ['10.00', '8.50'])
        self.assertEqual(result['daily'][0]['decrease'], '1.50')

    def test_missing_samples_are_empty_not_fabricated_and_accounts_are_isolated(self):
        self.assertEqual(self.history()['points'], [])
        self.record('4.20', self.start)
        other = replace(self.settings, deepseek_api_key='another-test-key')
        self.assertEqual(balances.balance_history(other, now=self.start + 300)['samples'], 0)
        self.assertEqual(self.history(currency='USD')['samples'], 0)

    def test_retention_does_not_change_user_data(self):
        users.init_db()
        users.update_user_fields(1, name='保留用户', bot_rating=123)
        self.record('10.00', self.start)
        self.record('9.00', self.start + int(timedelta(days=181).total_seconds()))
        with users.connect() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM deepseek_balance_samples').fetchone()[0], 1)
        self.assertEqual(users.get_user(1)['bot_rating'], 123)

    def test_non_finite_balance_is_rejected(self):
        with self.assertRaises(ValueError):
            self.record('NaN', self.start)
        self.assertEqual(self.history()['samples'], 0)

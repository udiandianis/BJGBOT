import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from scripts import napcat_watchdog
from tests.support import test_settings


class NapCatWatchdogTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.state_path = Path(directory.name) / 'state.json'
        process = patch.object(napcat_watchdog.subprocess, 'run', return_value=Mock(returncode=0))
        self.process = process.start()
        self.addCleanup(process.stop)
        client = patch.object(napcat_watchdog, 'NapCatClient')
        self.client = client.start().return_value
        self.addCleanup(client.stop)
        clock = patch.object(napcat_watchdog.time, 'time', return_value=10000)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        refresh = patch.object(napcat_watchdog, 'refresh_expired_qr', return_value=False)
        self.refresh = refresh.start()
        self.addCleanup(refresh.stop)

    def check(self):
        napcat_watchdog.check_login(test_settings(), self.state_path)

    def restarts(self):
        return [call for call in self.process.call_args_list if call.args[0][1] == 'restart']

    def test_three_failures_restart_once_then_preserve_qr(self):
        self.client.call.return_value = {'online': False}
        self.check()
        self.check()
        self.assertFalse(self.restarts())
        self.check()
        self.assertEqual(len(self.restarts()), 1)
        self.refresh.assert_not_called()
        self.clock.return_value += 3600
        self.check()
        self.assertEqual(len(self.restarts()), 1)
        self.refresh.assert_called_once()

    def test_online_rearms_recovery_and_cooldown_prevents_repeated_restarts(self):
        self.client.call.return_value = {'online': False}
        for _ in range(3):
            self.check()
        self.client.call.return_value = {'online': True}
        self.check()
        self.client.call.return_value = {'online': False}
        for _ in range(3):
            self.check()
        self.assertEqual(len(self.restarts()), 1)
        self.clock.return_value += 601
        self.check()
        self.assertEqual(len(self.restarts()), 2)

    def test_timeout_counts_as_failure_but_one_failure_is_not_enough(self):
        self.client.call.side_effect = requests.ConnectionError()
        self.check()
        self.assertEqual(json.loads(self.state_path.read_text())['failures'], 1)
        self.assertFalse(self.restarts())
        self.client.call.side_effect = None
        self.client.call.return_value = {'online': True}
        self.check()
        self.assertEqual(json.loads(self.state_path.read_text())['failures'], 0)

    def test_manual_stop_does_not_start_napcat(self):
        self.process.return_value.returncode = 3
        self.check()
        self.client.call.assert_not_called()
        self.assertFalse(self.state_path.exists())

    def test_corrupt_state_does_not_trigger_restart(self):
        self.state_path.write_text('invalid')
        with self.assertRaises(ValueError):
            self.check()
        self.assertFalse(self.restarts())

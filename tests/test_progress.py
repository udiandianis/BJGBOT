import unittest
from unittest.mock import Mock, MagicMock, call, patch

from src.services.progress import QueryProgress
from src.services import statistics, trainings


class QueryProgressTests(unittest.TestCase):
    def test_reports_current_counts_every_five_seconds(self):
        send = Mock()
        progress = QueryProgress(send)
        progress.update(13, 64)
        progress.stopped = Mock()
        progress.stopped.wait.side_effect = [False, False, True]
        send.side_effect = lambda _: progress.update(57, 64)
        progress.report()
        self.assertEqual(send.call_args_list, [call('当前进度 13/64'), call('当前进度 57/64')])
        self.assertEqual(progress.stopped.wait.call_args_list, [call(5)] * 3)

    def test_finished_or_stopped_query_sends_no_progress(self):
        send = Mock()
        progress = QueryProgress(send)
        progress.update(64, 64)
        progress.stopped = Mock()
        progress.stopped.wait.side_effect = [False, True]
        progress.report()
        send.assert_not_called()

    def test_context_stops_timer_on_failure(self):
        send = Mock()
        progress = QueryProgress(send)
        with self.assertRaises(ValueError):
            with progress as update:
                update(0, 64)
                raise ValueError('查询失败')
        self.assertTrue(progress.stopped.is_set())
        self.assertFalse(progress.thread.is_alive())
        send.assert_not_called()

    def test_success_reports_final_count_even_before_first_timer(self):
        send = Mock()
        progress = QueryProgress(send)
        with progress as update:
            update(0, 64)
            update(64, 64)
        send.assert_called_once_with('当前进度 64/64')
        self.assertFalse(progress.thread.is_alive())

    def test_statistics_counts_users_including_failed_queries(self):
        participants = [
            {'qq_id': 1, 'name': '用户一', 'class_name': '计算机2302', 'codeforces_handle': 'one', 'luogu_username': 'one'},
            {'qq_id': 2, 'name': '用户二', 'class_name': '计算机2302', 'codeforces_handle': 'two'},
            {'qq_id': 3, 'name': '用户三', 'class_name': '计算机2302'},
            {'qq_id': 4, 'name': None, 'codeforces_handle': 'excluded'},
        ]
        fetch = Mock(return_value={'today_accepted_submissions': 1, 'today_submissions': 2})
        failed = Mock(side_effect=ValueError('洛谷查询失败'))
        update = Mock()
        with patch.object(statistics.users, 'list_users', return_value=participants), \
             patch.object(statistics, 'PLATFORMS', {'CF': ('codeforces_handle', fetch), 'LG': ('luogu_username', failed)}):
            records, _ = statistics.collect_statistics(update)
        self.assertEqual(update.call_args_list, [call(0, 3), call(1, 3), call(2, 3), call(3, 3)])
        self.assertEqual(records[1]['errors'], ['LG'])
        self.assertEqual(fetch.call_count, 2)
        self.assertIsNone(records[2]['platforms']['LG'])
        self.assertNotIn(3, records)

    def test_statistics_requires_name_class_and_submissions_without_year_limit(self):
        participants = [
            {'qq_id': 1, 'name': '只有CF', 'class_name': '计算机2302', 'enrollment_year': 2023, 'codeforces_handle': 'active'},
            {'qq_id': 2, 'name': '今日无提交', 'class_name': '计算机2302', 'codeforces_handle': 'inactive'},
            {'qq_id': 3, 'name': None, 'codeforces_handle': 'unnamed'},
            {'qq_id': 4, 'name': '未绑定班级', 'codeforces_handle': 'active'},
            {'qq_id': 5, 'name': '没有入学年份', 'class_name': '测试班级', 'codeforces_handle': 'active'},
            {'qq_id': 6, 'name': '空班级', 'class_name': '', 'codeforces_handle': 'active'},
        ]
        fetch = Mock(side_effect=lambda platform, provider, handle: {'accepted': 0, 'submitted': int(handle == 'active')})
        with patch.object(statistics.users, 'list_users', return_value=participants), \
             patch.object(statistics, 'fetch_statistics', fetch):
            records, ranking = statistics.collect_statistics()
        self.assertEqual(set(records), {1, 5})
        self.assertEqual(ranking[0]['NAME'], '只有CF')
        self.assertEqual(fetch.call_count, 3)
        with patch.object(statistics.users, 'list_users', return_value=participants[1:]), \
             patch.object(statistics, 'fetch_statistics', return_value={'accepted': 0, 'submitted': 0}):
            with self.assertRaisesRegex(ValueError, '今日有提交'):
                statistics.collect_statistics()

    def test_training_counts_each_finished_user_including_failure(self):
        participants = [{'name': '用户一'}, {'name': '用户二'}]
        update = Mock()
        with patch.object(trainings, 'list_report_users', return_value=participants), \
             patch.object(trainings, 'load_training_problems', return_value={100: {'P1'}}), \
             patch.object(trainings, 'fetch_user_progress', side_effect=lambda user, problems: {'name': user['name'], 'failed': True}), \
             patch.object(trainings, 'configure_matplotlib'), \
             patch.object(trainings.pyplot, 'subplots', return_value=(Mock(), MagicMock())), \
             patch.object(trainings.pyplot, 'close'), \
             patch.object(trainings, 'REPORT_DIRECTORY'):
            trainings.get_png(update)
        self.assertEqual(update.call_args_list, [call(0, 2), call(1, 2), call(2, 2)])

    def test_report_distinguishes_unbound_zero_and_failure(self):
        record = {'NAME': '测试用户', 'platforms': {'CF': {'accepted': 0, 'submitted': 0}, 'LG': None, 'NK': None},
                  'errors': ['LG'], 'accepted': 0, 'submitted': 0, 'rank': '-'}
        figure, axes = Mock(), MagicMock()
        with patch.object(statistics, 'collect_statistics', return_value=({}, [record])), \
             patch.object(statistics, 'configure_matplotlib'), \
             patch.object(statistics.pyplot, 'subplots', return_value=(figure, axes)), \
             patch.object(statistics, 'save_report'):
            statistics.get_png()
        table = axes.table.call_args.kwargs
        cells = dict(zip(table['colLabels'], table['cellText'][0]))
        self.assertEqual(cells['CF'], '0/0')
        self.assertEqual(cells['LG'], '获取失败')
        self.assertEqual(cells['NK'], '暂未绑定')

    def test_training_report_displays_totals_and_completion_colors(self):
        problems = {key: set(range(4)) for key in trainings.TRAINING_LABELS}
        counts = {key: 0 for key in trainings.TRAINING_LABELS}
        counts.update({100: 4, 101: 3, 102: 1})
        record = {'name': '测试用户', 'failed': False, 'total': 8, 'by_training': counts}
        figure, axes = Mock(), MagicMock()
        with patch.object(trainings, 'list_report_users', return_value=[{'name': '测试用户'}]), \
             patch.object(trainings, 'load_training_problems', return_value=problems), \
             patch.object(trainings, 'fetch_user_progress', return_value=record), \
             patch.object(trainings, 'configure_matplotlib'), \
             patch.object(trainings.pyplot, 'subplots', return_value=(figure, axes)), \
             patch.object(trainings.pyplot, 'close'), patch.object(trainings, 'REPORT_DIRECTORY'):
            trainings.get_png()
        row = axes.table.call_args.kwargs['cellText'][0]
        self.assertEqual(row[1:5], ['4/4', '3/4', '1/4', '0/4'])
        self.assertEqual(row[-1], '8/72')
        report = axes.table.return_value
        self.assertIn(call('#14532d'), report.__getitem__.return_value.set_facecolor.call_args_list)
        self.assertIn(call('#ffffff'), report.__getitem__.return_value.set_facecolor.call_args_list)
        self.assertIn(call('#86efac'), report.__getitem__.return_value.set_facecolor.call_args_list)

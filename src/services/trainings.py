import threading
import re
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as pyplot
from src.adapters import http
from src.paths import REPORT_DIRECTORY
from src.fonts import configure_matplotlib
from src.settings import get_settings
from src.storage import users
from src.providers.luogu import page_data

TRAINING_LABELS = dict(zip(range(100, 118), ('顺序', '分支', '循环', '数组', '字串', '函数',
    '模拟', '排序', '暴力', '递归', '贪心', '二分', '搜索', '线性', '树', '集合', '图', '数学')))
_training_lock = threading.Lock()


def read_training_problems():
    """读取数据库中的题单题目，按题单编号分组。"""
    problems = {}
    with users.connect() as connection:
        for row in connection.execute('SELECT training_id, problem_id FROM luogu_training_problems'):
            problems.setdefault(row['training_id'], set()).add(row['problem_id'])
    return problems


def refresh_training_problems(only_if_missing=False):
    """完整下载后事务更新题单；任意请求失败都保留原有数据。"""
    settings = get_settings()
    with _training_lock:
        existing = read_training_problems()
        if only_if_missing and all(existing.get(training_id) for training_id in TRAINING_LABELS):
            return sum(len(problems) for problems in existing.values())
        downloaded = {}
        for training_id in TRAINING_LABELS:
            response = http.get(f'https://www.luogu.com.cn/training/{training_id}',
                                cookies=settings.luogu_cookies, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            problems = set(re.findall(r'href="/problem/([^"#?]+)', response.text))
            if not problems:
                raise ValueError(f'洛谷题单 {training_id} 无法读取')
            downloaded[training_id] = problems
        with users.connect() as connection:
            connection.execute('DELETE FROM luogu_training_problems')
            connection.executemany('INSERT INTO luogu_training_problems VALUES (?, ?)',
                                   [(training_id, problem_id) for training_id, problems in downloaded.items() for problem_id in problems])
        return sum(len(problems) for problems in downloaded.values())


def load_training_problems():
    """优先读取持久化题单，数据缺失时才首次下载。"""
    problems = read_training_problems()
    if not all(problems.get(training_id) for training_id in TRAINING_LABELS):
        refresh_training_problems(only_if_missing=True)
        problems = read_training_problems()
    return problems


def fetch_training_progress(username, problem_lists=None):
    """查询洛谷通过题目，返回各题单完成数和累计数；拒绝将访问错误当作零。"""
    if problem_lists is None:
        problem_lists = load_training_problems()
    settings = get_settings()
    with requests.Session() as session:
        session.cookies.update(settings.luogu_cookies)
        session.headers['User-Agent'] = 'Mozilla/5.0'
        response = session.get('https://www.luogu.com.cn/api/user/search', params={'keyword': username},
                               timeout=settings.request_timeout)
        response.raise_for_status()
        matches = response.json().get('users', [])
        if not matches:
            raise ValueError('未找到洛谷账号')
        user = next((user for user in matches if user.get('name') == username or str(user.get('uid')) == str(username)), matches[0])
        data = page_data(session, f'https://www.luogu.com.cn/user/{user["uid"]}/practice', settings.request_timeout)
    if 'passed' not in data:
        raise ValueError('洛谷通过题目数据不可用')
    passed = {problem['pid'] for problem in data['passed']}
    completed = {training_id: len(problems & passed) for training_id, problems in problem_lists.items()}
    return {'by_training': completed, 'total': sum(completed.values())}


def fetch_user_progress(user, problem_lists=None):
    """返回绑定用户的题单进度，抓取失败保留姓名和错误标记。"""
    try:
        return {'name': user['name'], **fetch_training_progress(user['luogu_username'], problem_lists), 'failed': False}
    except Exception:
        return {'name': user['name'], 'failed': True}


def list_report_users():
    """筛选已绑定姓名、洛谷账号并符合班级年份条件的报表用户。"""
    current_year = datetime.now(timezone(timedelta(hours=8))).year
    max_year_gap = get_settings().training_max_year_gap
    participants = [user for user in users.list_users()
                    if user.get('name') and user.get('luogu_username')
                    and (max_year_gap is None or (user.get('class_name')
                         and user.get('enrollment_year') is not None
                         and 0 <= current_year - user['enrollment_year'] <= max_year_gap))]
    if not participants:
        raise ValueError('暂无已绑定姓名和洛谷账号且符合班级年份条件的用户')
    return participants


def get_png(on_progress=None):
    """并发生成洛谷题单完成报告，失败用户显示查询失败，不使用旧图片。"""
    participants = list_report_users()
    problem_lists = load_training_problems()
    if on_progress:
        on_progress(0, len(participants))
    with ThreadPoolExecutor(max_workers=16) as executor:
        pending = [executor.submit(fetch_user_progress, user, problem_lists) for user in participants]
        records = []
        for future in as_completed(pending):
            records.append(future.result())
            if on_progress:
                on_progress(len(records), len(participants))
    records.sort(key=lambda record: (record['failed'], -record.get('total', 0)))
    total_problems = sum(len(problems) for problems in problem_lists.values())
    rows = []
    for record in records:
        row = {'姓名': record['name']}
        row.update({label: '-' if record['failed'] else f'{record["by_training"][training_id]}/{len(problem_lists[training_id])}'
                    for training_id, label in TRAINING_LABELS.items()})
        row['总计'] = '查询失败' if record['failed'] else f'{record["total"]}/{total_problems}'
        rows.append(row)
    configure_matplotlib()
    figure, axes = pyplot.subplots(figsize=(20, max(2.5, len(rows) * 0.5)))
    axes.axis('off')
    columns = list(rows[0])
    report = axes.table(cellText=[[row[column] for column in columns] for row in rows],
                        colLabels=columns, loc='center', cellLoc='center',
                        colWidths=[0.12] + [0.044] * 18 + [0.088])
    report.auto_set_font_size(False)
    report.set_fontsize(14)
    report.scale(1, 1.6)
    for row_index, record in enumerate(records, start=1):
        if record['failed']:
            report[row_index, 0].set_text_props(color='orange')
        else:
            counts = [(record['by_training'][training_id], len(problem_lists[training_id]))
                      for training_id in TRAINING_LABELS] + [(record['total'], total_problems)]
            for column, (completed, total) in enumerate(counts, start=1):
                fraction = min(1, completed / max(1, total))
                color = (1 - fraction, 1, 1 - fraction)
                report[row_index, column].set_facecolor(color)
                report[row_index, column].set_text_props(color='#111827')
    figure.tight_layout()
    REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    figure.savefig(REPORT_DIRECTORY / 'luogu.png', bbox_inches='tight', dpi=300)
    pyplot.close(figure)

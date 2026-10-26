import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as pyplot
from src.paths import REPORT_DIRECTORY
from src.fonts import configure_matplotlib
from src.storage import users
from src.providers import codeforces, luogu, nowcoder, atcoder

PLATFORMS = {'CF': ('codeforces_handle', codeforces.fetch_user_metrics), 'LG': ('luogu_username', luogu.fetch_user_metrics),
             'NK': ('nowcoder_handle', nowcoder.fetch_user_metrics), 'AT': ('atcoder_handle', atcoder.fetch_user_metrics)}
PLATFORM_LIMITS = {platform: threading.Semaphore(8) for platform in PLATFORMS}


def collect_statistics(on_progress=None):
    """并发采集用户今日统计并排名，抓取失败保留独立错误标记。"""
    records = {}
    pending_requests = {}
    participants = [user for user in users.list_users() if user.get('name') and user.get('class_name')]
    outstanding = {}
    completed = 0
    if on_progress:
        on_progress(0, len(participants))
    with ThreadPoolExecutor(max_workers=32) as executor:
        for user in participants:
            record = {'NAME': user['name'], 'platforms': {}, 'errors': [], 'accepted': 0, 'submitted': 0}
            records[user['qq_id']] = record
            outstanding[user['qq_id']] = 0
            for platform, (account_field, fetch_user) in PLATFORMS.items():
                if not user.get(account_field):
                    record['platforms'][platform] = None
                    continue
                future = executor.submit(fetch_statistics, platform, fetch_user, user[account_field])
                pending_requests[future] = (user['qq_id'], platform)
                outstanding[user['qq_id']] += 1
            if not outstanding[user['qq_id']]:
                completed += 1
        if on_progress:
            on_progress(completed, len(participants))
        for future in as_completed(pending_requests):
            user_id, platform = pending_requests[future]
            record = records[user_id]
            try:
                record['platforms'][platform] = future.result()
            except Exception:
                record['platforms'][platform] = None
                record['errors'].append(platform)
            outstanding[user_id] -= 1
            if not outstanding[user_id]:
                completed += 1
                if on_progress:
                    on_progress(completed, len(participants))
    for record in records.values():
        record['accepted'] = sum(metrics['accepted'] for metrics in record['platforms'].values() if metrics is not None)
        record['submitted'] = sum(metrics['submitted'] for metrics in record['platforms'].values() if metrics is not None)
    records = {user_id: record for user_id, record in records.items() if record['submitted'] > 0}
    if not records:
        raise ValueError('暂无已绑定姓名、班级且今日有提交的用户')
    ranking = sorted(records.values(), key=lambda record: (bool(record['errors']), -record['accepted'], -record['submitted']))
    previous_score, current_rank = None, 0
    for record in ranking:
        if record['errors']:
            record['rank'] = '-'
            continue
        score = (record['accepted'], record['submitted'])
        if score != previous_score:
            current_rank += 1
            previous_score = score
        record['rank'] = current_rank
    return records, ranking


def fetch_statistics(platform, fetch_user, handle):
    """限制单平台并发，返回账号今日通过和提交次数。"""
    with PLATFORM_LIMITS[platform]:
        metrics = fetch_user(handle)
    return {'accepted': int(metrics['today_accepted_submissions']), 'submitted': int(metrics['today_submissions'])}


def save_report(figure):
    """保存统计图片并关闭图表。"""
    REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_DIRECTORY / 'solve.png'
    figure.savefig(output_path, bbox_inches='tight', dpi=300)
    pyplot.close(figure)


def get_png(on_progress=None):
    """采集统计并生成表格图片，失败平台显示获取失败。"""
    _, ranking = collect_statistics(on_progress)
    rows = []
    for record in ranking:
        row = {'NAME': record['NAME']}
        for platform, metrics in record['platforms'].items():
            row[platform] = (f'{metrics["accepted"]}/{metrics["submitted"]}' if metrics is not None
                             else '获取失败' if platform in record['errors'] else '暂未绑定')
        row['ALL'] = '部分失败' if record['errors'] else f'{record["accepted"]}/{record["submitted"]}'
        row['RANK'] = record['rank']
        rows.append(row)
    configure_matplotlib()
    figure, axes = pyplot.subplots(figsize=(15, max(2.5, 0.6 * len(rows))))
    axes.axis('off')
    columns = list(rows[0])
    report_table = axes.table(cellText=[[row[column] for column in columns] for row in rows],
                             colLabels=columns, loc='center', cellLoc='center')
    report_table.auto_set_font_size(False)
    report_table.set_fontsize(16)
    report_table.scale(1, 1.6)
    for row_number, record in enumerate(ranking, start=1):
        color = 'orange' if record['errors'] else ('green' if not record['submitted'] else ('purple' if not record['accepted'] else 'black'))
        report_table[row_number, 0].set_text_props(color=color)
    figure.tight_layout()
    save_report(figure)

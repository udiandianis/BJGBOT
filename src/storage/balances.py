"""保存余额采样，并按实际相邻采样差额生成统计。"""
import hashlib
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from . import users

BEIJING_TIME = timezone(timedelta(hours=8))


def init_storage():
    """仅新增余额历史表，不修改既有用户或收藏数据。"""
    users.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with users.connect() as connection:
        connection.execute('''CREATE TABLE IF NOT EXISTS deepseek_balance_samples (
            series TEXT NOT NULL, currency TEXT NOT NULL, bucket INTEGER NOT NULL,
            sampled_at INTEGER NOT NULL, total_balance TEXT NOT NULL,
            granted_balance TEXT NOT NULL, topped_up_balance TEXT NOT NULL,
            PRIMARY KEY (series, currency, bucket))''')
        connection.execute('CREATE INDEX IF NOT EXISTS balance_samples_time ON deepseek_balance_samples(sampled_at)')
        connection.execute('CREATE INDEX IF NOT EXISTS balance_samples_series_time ON deepseek_balance_samples(series, currency, sampled_at)')


def account_series(settings):
    """用不可逆摘要隔离不同 API 配置的历史，不保存明文密钥。"""
    identity = settings.deepseek_base_url.rstrip('/') + '\0' + settings.deepseek_api_key
    return hashlib.sha256(identity.encode()).hexdigest()[:20]


def record_balance(settings, result, sampled_at=None):
    """每币种每五分钟最多一条，金额以十进制文本保存，保留 180 天。"""
    sampled_at = int(time.time() if sampled_at is None else sampled_at)
    rows = []
    for balance in result['balances']:
        amounts = [Decimal(balance[field]) for field in ('total_balance', 'granted_balance', 'topped_up_balance')]
        if not all(amount.is_finite() for amount in amounts):
            raise ValueError('余额不是有效金额')
        rows.append((account_series(settings), balance['currency'], sampled_at // 300, sampled_at,
                     *(format(amount, 'f') for amount in amounts)))
    with users.connect() as connection:
        connection.executemany('INSERT OR IGNORE INTO deepseek_balance_samples VALUES (?, ?, ?, ?, ?, ?, ?)', rows)
        connection.execute('DELETE FROM deepseek_balance_samples WHERE sampled_at < ?', (sampled_at - 180 * 86400,))


def balance_history(settings, days=7, currency='CNY', now=None):
    """按北京时间汇总采样差额；余额增加不直接认定为充值。"""
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now, BEIJING_TIME).replace(hour=0, minute=0, second=0, microsecond=0)
    start = int((today - timedelta(days=days - 1)).timestamp())
    series = account_series(settings)
    with users.connect() as connection:
        records = connection.execute('''SELECT sampled_at, total_balance FROM deepseek_balance_samples
            WHERE series=? AND currency=? AND sampled_at>=? AND sampled_at<=? ORDER BY sampled_at''',
            (series, currency, start, int(now))).fetchall()
        baseline = connection.execute('''SELECT sampled_at, total_balance FROM deepseek_balance_samples
            WHERE series=? AND currency=? AND sampled_at<? ORDER BY sampled_at DESC LIMIT 1''',
            (series, currency, start)).fetchone()
    previous = Decimal(baseline['total_balance']) if baseline else None
    daily = {}
    for record in records:
        amount = Decimal(record['total_balance'])
        day = datetime.fromtimestamp(record['sampled_at'], BEIJING_TIME).date().isoformat()
        bucket = daily.setdefault(day, {'date': day, 'samples': 0, 'decrease': Decimal(0), 'increase': Decimal(0)})
        delta = amount - previous if previous is not None else None
        bucket['samples'] += 1
        bucket['ending_balance'] = format(amount, 'f')
        if delta is not None:
            bucket['decrease'] += max(-delta, Decimal(0))
            bucket['increase'] += max(delta, Decimal(0))
        previous = amount
    decrease = sum((row['decrease'] for row in daily.values()), Decimal(0))
    increase = sum((row['increase'] for row in daily.values()), Decimal(0))
    rows = [{**row, 'decrease': format(row['decrease'], 'f'), 'increase': format(row['increase'], 'f')}
            for row in reversed(list(daily.values()))]
    points = [{'date': row['date'], 'balance': row['ending_balance'],
               'time': int(datetime.fromisoformat(row['date']).replace(tzinfo=BEIJING_TIME).timestamp())}
              for row in daily.values()]
    return {'currency': currency, 'days': days, 'points': points, 'daily': rows,
            'samples': len(records),
            'decrease': format(decrease, 'f'), 'increase': format(increase, 'f'),
            'first_sample_at': records[0]['sampled_at'] if records else None,
            'last_sample_at': records[-1]['sampled_at'] if records else None}

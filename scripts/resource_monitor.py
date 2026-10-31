"""每分钟记录轻量资源快照，供重启后排查内存和磁盘拥堵。"""
import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.paths import PROJECT_ROOT


def record_snapshot():
    """读取内核现有计数，不做磁盘压测；日志最多保留三个 1MiB 文件。"""
    values = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    memory = {key: int(values[key].split()[0]) for key in (
        'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree', 'Dirty', 'Writeback')}
    services = {}
    for unit in ('napcat', 'bjgbot-agent', 'bjgbot-agent-gateway', 'bjgbot', 'napcat-login'):
        root = Path('/sys/fs/cgroup/system.slice') / (unit + '.service')
        if root.exists():
            try:
                services[unit] = {'memory_bytes': int((root / 'memory.current').read_text()),
                                  'memory_events': (root / 'memory.events').read_text().strip(),
                                  'io': (root / 'io.stat').read_text().strip()}
                stat = dict(line.split() for line in (root / 'memory.stat').read_text().splitlines())
                services[unit]['memory_stat'] = {key: int(stat[key]) for key in (
                    'anon', 'file', 'file_mapped', 'workingset_refault_file', 'workingset_refault_anon') if key in stat}
                services[unit]['memory_pressure'] = (root / 'memory.pressure').read_text().strip()
                services[unit]['io_pressure'] = (root / 'io.pressure').read_text().strip()
            except FileNotFoundError:
                continue
    vmstat = dict(line.split() for line in Path('/proc/vmstat').read_text().splitlines())
    snapshot = {'time': datetime.now(timezone.utc).isoformat(),
                'uptime_seconds': float(Path('/proc/uptime').read_text().split()[0]), 'memory_kib': memory, 'services': services,
                'io_pressure': Path('/proc/pressure/io').read_text().strip(),
                'memory_pressure': Path('/proc/pressure/memory').read_text().strip(),
                'vmstat': {key: int(vmstat[key]) for key in ('pgmajfault', 'pswpin', 'pswpout')},
                'zswap': {key: path.read_text().strip() for key in ('enabled', 'max_pool_percent')
                          if (path := Path('/sys/module/zswap/parameters') / key).exists()}}
    directory = PROJECT_ROOT / 'output/logs'
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / 'resource-health.jsonl', maxBytes=1024 * 1024, backupCount=2, encoding='utf-8')
    logger = logging.getLogger('resource-health')
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        logger.info(json.dumps(snapshot, ensure_ascii=False))
    finally:
        logger.removeHandler(handler)
        handler.close()


if __name__ == '__main__':
    record_snapshot()

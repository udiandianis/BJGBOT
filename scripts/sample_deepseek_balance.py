"""独立采样 DS 余额，不依赖页面是否打开。"""
from src.settings import get_settings
from src.providers.ai import deepseek_balance
from src.storage.balances import init_storage, record_balance


if __name__ == '__main__':
    settings = get_settings()
    init_storage()
    record_balance(settings, deepseek_balance(settings))
    print('DS 余额采样完成')

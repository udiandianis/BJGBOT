"""从现有 JSON 读取凭据，通过环境变量交给 DSH，命令行和日志不含密钥。"""
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
config = json.loads((root / 'config/bot_settings.json').read_text(encoding='utf-8-sig'))
environment = dict(os.environ)
environment.update(DSH_HOME=str(root / '.agent/home'), AURABOT_WORKSPACE=str(root / '.agent/qq-chats'),
                   BJGBOT_AGENT_TOKEN=config['agent']['token'],
                   BJGBOT_BACKEND_URL=f"http://127.0.0.1:{config['bot']['port']}",
                   BJGBOT_DEEPSEEK_API_KEY=config['ai']['deepseek']['api_key'],
                   DSH_PERMISSION_MODE='danger-full-access', TZ='Asia/Shanghai')
environment['PATH'] = str(root / '.agent/node/bin') + os.pathsep + str(root / '.agent/host/node_modules/.bin') + os.pathsep + environment['PATH']
node = str(root / '.agent/node/bin/node')
if len(sys.argv) > 1 and sys.argv[1] == 'gateway':
    arguments = [node, str(root / 'scripts/agent_gateway.mjs')]
else:
    # 社区只支持一个主人，账号统一取现有配置的首位机器人管理员。
    if not config['collections']['admins']:
        raise RuntimeError('请先配置 collections.admins，首位管理员作为社区主人')
    community_config = root / '.agent/home/plugins-data/aurabot/config.json'
    community = json.loads(community_config.read_text(encoding='utf-8'))
    owner_qq = str(config['collections']['admins'][0])
    if community.get('ownerQQ') != owner_qq:
        community['ownerQQ'] = owner_qq
        community_config.write_text(json.dumps(community, ensure_ascii=False, indent=2), encoding='utf-8')
    arguments = [node, str(root / '.agent/host/node_modules/@deepseek-ai/dsh/lib/bin.js'),
                 '--profile', 'web', '--patch', str(root / '.agent/home/bjgbot-model.patch.json'),
                 '--host', '127.0.0.1', '--port', '3080', '--no-open']
os.chdir(root)
os.execve(node, arguments, environment)

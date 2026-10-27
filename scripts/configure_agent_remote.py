"""配置社区本体；复用原 DeepSeek Key，后续运行保留群开关和社区配置。"""
from datetime import datetime
import json
from pathlib import Path
import secrets
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
path = root / 'config/bot_settings.json'
config = json.loads(path.read_text(encoding='utf-8-sig'))
if not config['collections']['admins']:
    raise RuntimeError('请先配置 collections.admins，首位管理员作为 Agent 管理员')
owner_qq = str(config['collections']['admins'][0])
backup = root / 'output/deployment' / ('pre-agent-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
shutil.copy2(path, backup / path.name)

# 固定社区版本的提示文字适配；权限校验代码不作修改，重复部署不会重复应用。
apply_args = ['git', 'apply', '--directory=.agent/aurabot']
for patch_name in ('permission-only.patch', 'empty-message.patch', 'quoted-and-recent-images.patch', 'image-send-result.patch', 'image-backend-fallback.patch', 'group-interjection.patch'):
    patch_bytes = (root / 'resources/agent/community' / patch_name).read_text(encoding='utf-8').encode()
    applied = subprocess.run([*apply_args, '--reverse', '--check'], input=patch_bytes,
                             cwd=root, capture_output=True).returncode == 0
    if not applied:
        subprocess.run(apply_args, input=patch_bytes, cwd=root, check=True)

# 现有官方接口的旧别名已由服务端转到 Flash，改为官方模型列表中的正式名称。
if config['ai']['deepseek']['model'] == 'deepseek-chat':
    config['ai']['deepseek']['model'] = 'deepseek-flash'
token = config.get('agent', {}).get('token') or secrets.token_urlsafe(32)
config['agent'] = {'enabled': True, 'base_url': 'http://127.0.0.1:3080/aurabot/api/ext/bjgbot', 'token': token}
path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
path.chmod(0o600)
home = root / '.agent/home'
data = home / 'plugins-data/aurabot'
data.mkdir(parents=True, exist_ok=True)
aurabot_path = data / 'config.json'
first = not aurabot_path.exists()
aurabot = json.loads(aurabot_path.read_text()) if not first else {}
# 此字段仅为社区权限说明提供角色名称，日常称呼由人格卡决定。
if aurabot.get('ownerName', '主人') in ('', '主人'):
    aurabot['ownerName'] = '管理员'
aurabot.update(enabled=True, dryRun=False, setupDone=True, botQQ=str(config['bot']['qq']),
               ownerQQ=owner_qq, ownerLevel='full',
               model={'provider': 'deepseek-official', 'model': config['ai']['deepseek']['model'], 'reasoningEffort': 'low'})
aurabot['snowluma'] = dict(aurabot.get('snowluma', {}), autoStart=False, autoAttach=False,
                           httpUrl='http://127.0.0.1:5030/onebot', wsUrl='ws://127.0.0.1:5030/onebot',
                           httpToken=token, wsToken=token)
if first:
    aurabot['allow'] = {'private': [], 'groups': []}
    aurabot['imageGen'] = {'ownerOnly': False}
    # 本次接入针对群聊；空间发布、站外互动、私聊定时推送尚未配置。
    for key in ('diary', 'qzoneSocial', 'bili', 'speakUp'):
        aurabot[key] = {'enabled': False}
aurabot_path.write_text(json.dumps(aurabot, ensure_ascii=False, indent=2), encoding='utf-8')
aurabot_path.chmod(0o600)
module = data / 'modules/bjgbot'
module.mkdir(parents=True, exist_ok=True)
shutil.copy2(root / 'resources/agent/bjgbot/index.mjs', module / 'index.mjs')
web_stickers = data / 'modules/web-stickers'
web_stickers.mkdir(parents=True, exist_ok=True)
shutil.copy2(root / 'resources/agent/web-stickers/index.mjs', web_stickers / 'index.mjs')
vision_assist = data / 'modules/vision-assist'
vision_assist.mkdir(parents=True, exist_ok=True)
shutil.copy2(root / 'resources/agent/vision-assist/index.mjs', vision_assist / 'index.mjs')
profile = home / 'profiles/web/cordis.patch.yml'
shutil.copy2(profile, backup / 'dsh-cordis.patch.yml')
patch_path = home / 'bjgbot-model.patch.json'
patch = [
    {'id': 'llm-deepseek', 'config': {
        'apiKeyEnv': 'BJGBOT_DEEPSEEK_API_KEY',
        'baseURL': config['ai']['deepseek']['base_url'].rstrip('/').removesuffix('/v1') + '/anthropic',
    }},
    {'id': 'agent-default-model', 'config': {'provider': 'deepseek-official', 'model': config['ai']['deepseek']['model']}},
]
patch_path.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'configured': True, 'owner': owner_qq, 'groups': aurabot.get('allow', {}).get('groups', []),
                  'backup': str(backup)}, ensure_ascii=False))

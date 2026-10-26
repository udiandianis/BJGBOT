"""安装固定版本的 DSH 与 Aurabot；仅安装文件，不启动或发 QQ 消息。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.agent'
COMMIT = '062f3653df7091344756168078f28ea87934d9c0'
DSH_VERSION = '0.2.1-rc.2'
NODE_VERSION = 'v24.22.1'


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'BJGBOT-agent-setup'})
    return urllib.request.urlopen(request, timeout=120).read()


def install():
    RUNTIME.mkdir(exist_ok=True)
    version = NODE_VERSION
    archive_name = f'node-{version}-linux-x64.tar.xz'
    node_root = RUNTIME / archive_name.removesuffix('.tar.xz')
    if not (node_root / 'bin/npm').exists():
        checksums = fetch(f'https://nodejs.org/dist/{version}/SHASUMS256.txt').decode()
        expected = next(line.split()[0] for line in checksums.splitlines() if line.endswith('  ' + archive_name))
        content = fetch(f'https://nodejs.org/dist/{version}/{archive_name}')
        if hashlib.sha256(content).hexdigest() != expected:
            raise RuntimeError('Node.js SHA256 mismatch')
        archive = RUNTIME / archive_name
        archive.write_bytes(content)
        # 校验通过的官方包包含 npm 相对符号链接；旧 Python 的 data filter 会误拒绝。
        subprocess.run(['tar', '-xJf', str(archive), '-C', str(RUNTIME)], check=True)
    link = RUNTIME / 'node'
    if not link.exists():
        link.symlink_to(node_root.name, target_is_directory=True)
    plugin = RUNTIME / 'aurabot'
    if not plugin.exists():
        archive = RUNTIME / 'aurabot.tar.gz'
        content = fetch(f'https://codeload.github.com/accomplish07zrh-eng/dsh-aurabot-qq/tar.gz/{COMMIT}')
        archive.write_bytes(content)
        with tarfile.open(archive) as package:
            package.extractall(RUNTIME, filter='data')
        (RUNTIME / ('dsh-aurabot-qq-' + COMMIT)).rename(plugin)
        (RUNTIME / 'aurabot-source.json').write_text(json.dumps({
            'commit': COMMIT, 'archive_sha256': hashlib.sha256(content).hexdigest()}, indent=2))
    npm_root = RUNTIME / 'host'
    npm_root.mkdir(exist_ok=True)
    (npm_root / 'package.json').write_text(json.dumps({
        'name': 'bjgbot-agent-host', 'private': True, 'type': 'module',
        'dependencies': {'@deepseek-ai/dsh': DSH_VERSION, 'ws': '8.21.3', 'pnpm': '11.28.5'}}, indent=2))
    environment = dict(os.environ, PATH=str(link / 'bin') + os.pathsep + os.environ['PATH'])
    subprocess.run([str(link / 'bin/npm'), 'install', '--omit=dev', '--no-audit', '--no-fund'],
                   cwd=npm_root, env=environment, check=True)
    environment['PATH'] = str(npm_root / 'node_modules/.bin') + os.pathsep + environment['PATH']
    environment['DSH_HOME'] = str(RUNTIME / 'home')
    registration = RUNTIME / 'home/profiles/web/package.json'
    if not registration.exists() or str(plugin) not in registration.read_text():
        subprocess.run([str(npm_root / 'node_modules/.bin/dsh'), 'plugin', '--profile', 'web',
                        'add', str(plugin)], cwd=ROOT, env=environment, check=True)
    print(json.dumps({'node': version, 'dsh': DSH_VERSION, 'aurabot': COMMIT}), flush=True)


if __name__ == '__main__':
    install()

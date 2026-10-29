import hmac
import logging
import secrets
import subprocess
import threading
import time
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_file, session
from werkzeug.security import check_password_hash

from ..adapters.napcat import NapCatClient
from ..settings import get_settings
from ..providers.ai import deepseek_balance
from ..storage import balances

logger = logging.getLogger(__name__)


def create_login_app(settings=None, client=None):
    """创建仅提供密码登录、状态和二维码的独立应用。"""
    settings = settings or get_settings()
    config = settings.login_page
    require_password = config.get('require_password', True)
    if (require_password and not config.get('password_hash')) or len(config.get('session_secret', '')) < 32 or not config.get('qr_path'):
        raise ValueError('请在 login_page 中配置密码哈希、会话密钥和二维码路径')
    balances.init_storage()
    client = client or NapCatClient(replace(settings, request_timeout=3))
    app = Flask(__name__, static_url_path='/assets')
    app.config.update(SECRET_KEY=config['session_secret'], SESSION_COOKIE_NAME='bot_login',
                      SESSION_COOKIE_SECURE=config.get('secure_cookie', True), SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                      PERMANENT_SESSION_LIFETIME=timedelta(days=7), MAX_CONTENT_LENGTH=8192)
    qr_path = Path(config['qr_path'])
    lock = threading.Lock()
    attempts = []
    last_refresh = 0
    balance_cache = {'updated_at': 0, 'data': None}
    balance_lock = threading.Lock()
    status_cache = {'checked_at': None, 'online': False}
    status_lock = threading.Lock()
    history_cache = {}
    history_lock = threading.Lock()

    def online():
        """合并三秒内的重复检查，避免多个手机页面同时请求 QQ。"""
        with status_lock:
            now = time.monotonic()
            if status_cache['checked_at'] is not None and now - status_cache['checked_at'] < 3:
                return status_cache['online']
            try:
                status = client.call('get_status')
                active = isinstance(status, dict) and status.get('online') is True
            except Exception:
                active = False
            status_cache.update(checked_at=now, online=active)
            return active

    @app.before_request
    def verify_access():
        """按配置验证访问；公开页面只读，禁止远程重启 QQ。"""
        if not require_password and request.method == 'POST':
            return jsonify(error='公开页面仅供查看，不允许重启或修改登录状态'), 403
        if request.endpoint != 'static':
            session.setdefault('csrf', secrets.token_urlsafe(32))
        if require_password and request.endpoint not in ('index', 'static') and not session.get('authenticated'):
            return jsonify(error='请先输入访问密码'), 401
        if request.method == 'POST':
            token = request.headers.get('X-CSRF-Token') or request.form.get('csrf', '')
            if not hmac.compare_digest(token, session.get('csrf', '')):
                return jsonify(error='页面已过期，请刷新后重试'), 403

    @app.after_request
    def security_headers(response):
        """禁止缓存二维码，并限制页面资源和嵌入来源。"""
        response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                                 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
                                 'Content-Security-Policy': "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"})
        return response

    @app.route('/', methods=['GET', 'POST'])
    def index():
        """校验独立访问密码，不使用 QQ 密码或 NapCat 管理令牌。"""
        error = None
        status = 200
        if request.method == 'POST':
            now = time.time()
            with lock:
                attempts[:] = [when for when in attempts if now - when < 900]
                if len(attempts) >= 5:
                    error, status = '尝试次数过多，请在 15 分钟后重试', 429
                elif check_password_hash(config['password_hash'], request.form.get('password', '')):
                    session.clear()
                    session.update(authenticated=True, csrf=secrets.token_urlsafe(32))
                    session.permanent = True
                    attempts.clear()
                    return redirect('/')
                else:
                    attempts.append(now)
                    error, status = '访问密码不正确，请重试', 401
        return render_template('login.html', authenticated=not require_password or session.get('authenticated', False),
                               require_password=require_password, csrf=session['csrf'], error=error), status

    @app.get('/status')
    def status():
        """只返回登录状态和新鲜二维码的修改时间。"""
        active = online()
        try:
            modified = qr_path.stat().st_mtime
        except FileNotFoundError:
            modified = 0
        available = not active and modified >= last_refresh and 0 <= time.time() - modified < 120
        return jsonify(online=active, qr_available=available, updated_at=int(modified) if available else None,
                       can_refresh=require_password)

    @app.get('/qrcode.png')
    def qrcode():
        """仅提供当前有效二维码，在线或过期时不返回旧图片。"""
        if online():
            return jsonify(error='QQ 已在线，无需扫码'), 409
        try:
            modified = qr_path.stat().st_mtime
            if modified < last_refresh or not 0 <= time.time() - modified < 120:
                return jsonify(error='二维码已过期，请获取新二维码'), 410
            return send_file(qr_path, mimetype='image/png', as_attachment=request.args.get('download') == '1',
                             download_name='QQ-login.png', conditional=False, max_age=0)
        except FileNotFoundError:
            return jsonify(error='二维码正在生成，请稍候'), 404

    @app.post('/refresh')
    def refresh():
        """离线时允许主动刷新二维码，两次操作至少间隔两分钟。"""
        nonlocal last_refresh
        if online():
            return jsonify(error='QQ 已在线，无需重新登录'), 409
        with lock:
            now = time.time()
            if now - last_refresh < 120:
                return jsonify(error='正在等待登录，请稍后再获取新二维码'), 429
            last_refresh = now
        try:
            subprocess.run(['systemctl', 'restart', 'napcat.service'], check=True, timeout=45)
        except (subprocess.SubprocessError, OSError):
            logger.exception('手机登录页刷新二维码失败')
            return jsonify(error='暂时无法刷新二维码，请稍后重试'), 503
        return jsonify(ok=True)

    @app.post('/logout')
    def logout():
        """只退出手机管理页面，不退出 QQ。"""
        session.clear()
        return redirect('/')

    @app.get('/balance')
    def balance():
        """登录后查询 DS 余额，最多每分钟向服务商请求一次。"""
        with balance_lock:
            if time.time() - balance_cache['updated_at'] < 60 and balance_cache['data'] is not None:
                return jsonify(**balance_cache['data'], updated_at=balance_cache['updated_at'])
            try:
                data = deepseek_balance(settings)
                balances.record_balance(settings, data)
                with history_lock:
                    history_cache.clear()
            except Exception:
                return jsonify(error='DS 余额暂时无法查询，请稍后重试'), 503
            balance_cache.update(updated_at=int(time.time()), data=data)
            return jsonify(**data, updated_at=balance_cache['updated_at'])

    @app.get('/balance-history')
    def history():
        """查询有限时间范围的余额变化，沿用页面访问权限。"""
        days = request.args.get('days', '7')
        currency = request.args.get('currency', 'CNY')
        if len(days) > 3 or not days.isdecimal() or not 1 <= int(days) <= 180 or currency not in ('CNY', 'USD'):
            return jsonify(error='请输入 1 到 180 的整数天数，并选择有效币种'), 400
        days = int(days)
        with history_lock:
            key = (days, currency)
            cached = history_cache.get(key)
            if cached and time.monotonic() - cached['checked_at'] < 30:
                return jsonify(cached['data'])
            data = balances.balance_history(settings, days, currency)
            history_cache[key] = {'checked_at': time.monotonic(), 'data': data}
            return jsonify(data)

    return app


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    settings = get_settings()
    create_login_app(settings).run(host=settings.login_page.get('host', '127.0.0.1'),
                                   port=settings.login_page.get('port', 5011))

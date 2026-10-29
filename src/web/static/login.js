const statusText = document.querySelector('#status');
const message = document.querySelector('#message');
const qrArea = document.querySelector('#qr-area');
const qrImage = document.querySelector('#qrcode');
const onlineMark = document.querySelector('#online-mark');
const refresh = document.querySelector('#refresh');
const feedback = document.querySelector('#feedback');
let busy = false;
let qrVersion = null;

async function updateStatus() {
  if (busy || document.hidden) return;
  busy = true;
  try {
    const response = await fetch('/status', {cache: 'no-store'});
    if (response.status === 401) { location.reload(); return; }
    if (!response.ok) throw new Error('暂时无法获取状态，请稍后重试。');
    const state = await response.json();
    qrArea.hidden = !state.qr_available;
    onlineMark.hidden = !state.online;
    refresh.hidden = state.online || !state.can_refresh;
    statusText.textContent = state.online ? 'QQ 已在线' : state.qr_available ? '等待扫码登录' : '需要重新登录';
    message.textContent = state.online ? '机器人已连接，无需扫码。' : state.qr_available ? '请使用当前二维码完成手机 QQ 授权。' : state.can_refresh ? '当前没有可用二维码，点击下方按钮获取。' : '正在等待自动恢复或更新二维码，请稍候，页面会自动刷新。';
    if (state.qr_available && qrVersion !== state.updated_at) {
      qrVersion = state.updated_at;
      qrImage.src = `/qrcode.png?v=${qrVersion}`;
    }
    if (!state.qr_available) { qrVersion = null; qrImage.removeAttribute('src'); }
  } catch (error) {
    statusText.textContent = '暂时无法连接';
    message.textContent = error.message;
    qrArea.hidden = true;
    onlineMark.hidden = true;
  } finally { busy = false; }
}

refresh.addEventListener('click', async () => {
  refresh.disabled = true;
  refresh.textContent = '正在生成二维码…';
  feedback.textContent = '';
  try {
    const response = await fetch('/refresh', {method: 'POST', headers: {'X-CSRF-Token': document.querySelector('meta[name=csrf-token]').content}});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '获取失败，请稍后重试。');
    message.textContent = '二维码正在生成，请稍候。';
    await updateStatus();
  } catch (error) { feedback.textContent = error.message; }
  finally { refresh.disabled = false; refresh.textContent = '获取新二维码'; }
});
qrImage.addEventListener('error', () => { qrArea.hidden = true; qrVersion = null; });
updateStatus();
setInterval(updateStatus, 5000);

const balanceRefresh = document.querySelector('#balance-refresh');
async function updateBalance() {
  if (balanceRefresh.disabled || document.hidden) return;
  balanceRefresh.disabled = true;
  try {
    const response = await fetch('/balance', {cache: 'no-store'});
    if (response.status === 401) { location.reload(); return; }
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '余额暂时无法查询');
    const money = row => `${row.currency === 'CNY' ? '¥' : row.currency === 'USD' ? '$' : row.currency + ' '}${row.total_balance}`;
    document.querySelector('#balance-amount').textContent = result.balances.map(money).join(' / ');
    document.querySelector('#balance-detail').textContent = result.balances.map(row => `赠金 ${row.granted_balance} · 充值余额 ${row.topped_up_balance} ${row.currency}`).join('\n') + (result.available ? '' : '\n当前账号无可用余额');
    document.querySelector('#balance-updated').textContent = `更新于 ${new Date(result.updated_at * 1000).toLocaleTimeString('zh-CN', {hour12: false})}`;
    document.dispatchEvent(new CustomEvent('balance-updated', {detail: result.balances.map(row => row.currency)}));
  } catch (error) {
    document.querySelector('#balance-amount').textContent = '暂时无法查询';
    document.querySelector('#balance-detail').textContent = error.message;
  } finally { balanceRefresh.disabled = false; }
}
updateBalance();
setInterval(updateBalance, 60000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) { updateStatus(); updateBalance(); } });

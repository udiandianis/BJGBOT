const historyChart = document.querySelector('#history-chart');
const historyCaption = document.querySelector('#history-caption');
const historyCurrency = document.querySelector('#history-currency');
const rangeButtons = [...document.querySelectorAll('.history-ranges button')];
let historyDays = 7;
let historyLoading = false;
let chartPoints = [];
let chartCoordinates = [];

const historyNumber = value => new Intl.NumberFormat('zh-CN', {minimumFractionDigits: 2, maximumFractionDigits: 6}).format(Number(value));
const historyMoney = value => `${historyCurrency.value === 'CNY' ? '¥' : '$'}${historyNumber(value)}`;

function svgElement(tag, attributes, text) {
  const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  if (text !== undefined) element.textContent = text;
  return element;
}

function selectChartPoint(index) {
  const point = chartPoints[index];
  if (!point) return;
  const marker = historyChart.querySelector('#history-marker');
  marker.setAttribute('cx', chartCoordinates[index][0]);
  marker.setAttribute('cy', chartCoordinates[index][1]);
  historyCaption.textContent = `${point.date} · ${historyMoney(point.balance)}`;
}

function drawHistory(points) {
  historyChart.replaceChildren();
  historyChart.toggleAttribute('hidden', !points.length);
  chartPoints = points;
  if (!points.length) {
    historyCaption.textContent = '暂无记录，后台会自动采样。';
    return;
  }
  const values = points.map(point => Number(point.balance));
  const minimum = Math.min(...values), maximum = Math.max(...values);
  historyChart.setAttribute('aria-label', `${points.length} 天余额记录，最高 ${historyMoney(maximum)}，最低 ${historyMoney(minimum)}`);
  const padding = Math.max((maximum - minimum) * 0.12, 0.005);
  const low = minimum - padding, high = maximum + padding;
  const first = points[0].time, last = points[points.length - 1].time;
  const left = 65, right = 312, top = 14, bottom = 145;
  chartCoordinates = points.map((point, index) => [
    points.length === 1 ? (left + right) / 2 : left + (point.time - first) / Math.max(1, last - first) * (right - left),
    bottom - (values[index] - low) / (high - low) * (bottom - top)
  ]);
  for (const value of [...new Set([maximum, minimum])]) {
    const y = bottom - (value - low) / (high - low) * (bottom - top);
    historyChart.append(svgElement('line', {x1: left, x2: right, y1: y, y2: y, stroke: '#dce5dc', 'stroke-dasharray': '3 4'}));
    historyChart.append(svgElement('text', {x: left - 8, y: y + 4, 'text-anchor': 'end', fill: '#647269', 'font-size': 11}, historyNumber(value)));
  }
  if (points.length > 1) {
    historyChart.append(svgElement('polyline', {points: chartCoordinates.map(point => point.join(',')).join(' '),
      fill: 'none', stroke: '#23815b', 'stroke-width': 2.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}));
  }
  const dateLabel = time => new Date(time * 1000).toLocaleDateString('zh-CN', {timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric'});
  historyChart.append(svgElement('text', {x: left, y: 169, fill: '#647269', 'font-size': 11}, dateLabel(first)));
  if (points.length > 1) historyChart.append(svgElement('text', {x: right, y: 169, 'text-anchor': 'end', fill: '#647269', 'font-size': 11}, dateLabel(last)));
  historyChart.append(svgElement('circle', {id: 'history-marker', r: 4.5, fill: '#176644', stroke: 'white', 'stroke-width': 2}));
  selectChartPoint(points.length - 1);
}

function historyRows(target, rows, width, empty) {
  target.replaceChildren();
  for (const cells of rows) {
    const row = document.createElement('tr');
    for (const value of cells) {
      const cell = document.createElement('td');
      cell.textContent = value;
      row.append(cell);
    }
    target.append(row);
  }
  if (!rows.length) {
    const row = document.createElement('tr'), cell = document.createElement('td');
    cell.colSpan = width;
    cell.textContent = empty;
    row.append(cell);
    target.append(row);
  }
}

async function loadHistory() {
  if (historyLoading || document.hidden) return;
  historyLoading = true;
  const currency = historyCurrency.value, days = historyDays;
  try {
    const response = await fetch(`/balance-history?days=${days}&currency=${currency}`, {cache: 'no-store'});
    if (response.status === 401) { location.reload(); return; }
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '暂时无法读取历史记录');
    if (currency !== historyCurrency.value || days !== historyDays) return;
    drawHistory(result.points);
    historyRows(document.querySelector('#history-daily'), result.daily.map(row => [
      row.date.slice(5), historyNumber(row.decrease), historyNumber(row.increase), historyNumber(row.ending_balance)
    ]), 4, '暂无采样记录');
  } catch (error) { historyCaption.textContent = error.message; }
  finally {
    historyLoading = false;
    if (currency !== historyCurrency.value || days !== historyDays) loadHistory();
  }
}

for (const button of rangeButtons) button.addEventListener('click', () => {
  historyDays = Number(button.dataset.days);
  for (const other of rangeButtons) other.setAttribute('aria-pressed', String(other === button));
  loadHistory();
});
historyCurrency.addEventListener('change', loadHistory);
historyChart.addEventListener('pointermove', event => {
  if (!chartPoints.length) return;
  const x = (event.clientX - historyChart.getBoundingClientRect().left) / historyChart.getBoundingClientRect().width * 320;
  let closest = 0;
  for (let i = 1; i < chartCoordinates.length; i++) if (Math.abs(chartCoordinates[i][0] - x) < Math.abs(chartCoordinates[closest][0] - x)) closest = i;
  selectChartPoint(closest);
});
document.addEventListener('balance-updated', event => {
  const current = historyCurrency.value;
  historyCurrency.replaceChildren(...event.detail.map(currency => {
    const option = document.createElement('option'); option.value = currency; option.textContent = currency === 'CNY' ? '人民币' : '美元'; return option;
  }));
  if (event.detail.includes(current)) historyCurrency.value = current;
  historyCurrency.hidden = event.detail.length < 2;
  loadHistory();
});
document.addEventListener('visibilitychange', () => { if (!document.hidden) loadHistory(); });
loadHistory();

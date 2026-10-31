// 适配现有 NapCat HTTP。WS 仅提供连接状态；消息统一由 BJGBOT 分流后送到 Aurabot。
import { createServer } from 'node:http'
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import { resolve, dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { authorised } from '../resources/agent/bjgbot/index.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(join(root, '.agent/host/package.json'))
const { WebSocketServer } = require('ws')
const config = JSON.parse(readFileSync(join(root, 'config/bot_settings.json'), 'utf8').replace(/^\uFEFF/, ''))
const agentConfig = join(root, '.agent/home/plugins-data/aurabot/config.json')
const token = config.agent.token
const current = () => JSON.parse(readFileSync(agentConfig, 'utf8'))
const server = createServer(async (req, res) => {
  const reply = (status, value) => { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(value)) }
  if (!authorised(req.headers.authorization, token)) return reply(401, { retcode: 1401, message: 'Unauthorized' })
  const action = new URL(req.url, 'http://localhost').pathname.replace(/^\/onebot\//, '')
  if (!/^[a-zA-Z0-9_]+$/.test(action)) return reply(404, { retcode: 1404 })
  try {
    const chunks = []
    for await (const chunk of req) chunks.push(chunk)
    const payload = Buffer.concat(chunks)
    chunks.length = 0
    let params = JSON.parse(payload.toString() || '{}')
    const cfg = current()
    if (params.group_id != null && /^(send_|set_group_|delete_msg)/.test(action)
        && !cfg.allow.groups.includes(String(params.group_id))) {
      return reply(200, { status: 'failed', retcode: 1403, message: '本群 Agent 已关闭' })
    }
    params = null
    const upstream = await fetch(config.napcat.api_url.replace(/\/+$/, '') + '/' + action, {
      method: 'POST', headers: { 'content-type': 'application/json', authorization: 'Bearer ' + config.napcat.api_token },
      body: payload.length ? payload : Buffer.from('{}'), signal: AbortSignal.timeout(30_000),
    })
    const data = await upstream.json()
    reply(upstream.status, data)
  } catch (error) {
    console.error('NapCat relay failed:', error.name)
    reply(502, { status: 'failed', retcode: 1502, message: 'NapCat relay unavailable' })
  }
})
const ws = new WebSocketServer({ noServer: true })
server.on('upgrade', (req, socket, head) => {
  const url = new URL(req.url, 'http://localhost')
  const value = req.headers.authorization || ('Bearer ' + (url.searchParams.get('access_token') || ''))
  if (!authorised(value, token)) return socket.destroy()
  ws.handleUpgrade(req, socket, head, (peer) => ws.emit('connection', peer, req))
})
ws.on('connection', (peer) => {
  peer.send(JSON.stringify({ time: Math.floor(Date.now() / 1000), self_id: config.bot.qq,
    post_type: 'meta_event', meta_event_type: 'lifecycle', sub_type: 'connect' }))
})
server.listen(5030, '127.0.0.1', () => console.log('BJGBOT NapCat relay listening on 127.0.0.1:5030'))
export { server }

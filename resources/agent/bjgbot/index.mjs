// Aurabot 用户扩展：适配 BJGBOT 路由、逐群开关和权限身份说明，记忆与接话由社区处理。
import { timingSafeEqual } from 'node:crypto'

export function authorised(header, token) {
  if (!token) return false
  const actual = Buffer.from(String(header || ''))
  const expected = Buffer.from('Bearer ' + token)
  return actual.length === expected.length && timingSafeEqual(actual, expected)
}

export function setGroup(config, group, enabled) {
  const groups = new Set(config.allow.groups.map(String))
  enabled ? groups.add(String(group)) : groups.delete(String(group))
  return { ...config, allow: { ...config.allow, groups: [...groups] } }
}

export default {
  id: 'bjgbot', name: 'BJGBOT 接入', version: '1.0.0',
  description: '保留 BJGBOT 原有指令，机器人管理员逐群开启或关闭社区 Agent',
  setup(api) {
    const token = process.env.BJGBOT_AGENT_TOKEN || ''
    const owner = String(api.config().ownerQQ)
    const seen = new Map()
    let commands = ''
    const enabled = (id) => api.config().allow.groups.map(String).includes(String(id))
    const check = (req) => authorised(req.headers.authorization, token)
    const denied = { ok: false, message: 'Unauthorized' }

    // 指令说明从现有路由实时读取；人格与规则通过社区原生接口管理。
    const loadCommands = async () => {
      try {
        const url = process.env.BJGBOT_BACKEND_URL || 'http://127.0.0.1:5010'
        const r = await fetch(url + '/agent/commands', {
          headers: { authorization: 'Bearer ' + token }, signal: AbortSignal.timeout(5000),
        })
        if (!r.ok) return
        const data = await r.json()
        if (data.ok && typeof data.commands === 'string') commands = data.commands
      } catch {}
    }
    loadCommands()
    api.every(60_000, loadCommands, '同步 BJGBOT 指令说明')
    api.rule(() => commands ? '你所在的 QQ 机器人还提供以下 BJGBOT 业务指令，你可以记住这些功能，按需要告诉群友如何使用：\n' + commands : '')

    api.route('/control', async (req) => {
      if (!check(req)) return denied
      const body = await api.core.http.body(req)
      if (String(body.user_id) !== owner) return { ok: false, message: '仅机器人管理员可操作' }
      const group = String(body.group_id || '')
      if (!/^[1-9]\d*$/.test(group) || !['START', 'END'].includes(body.action)) return { ok: false, message: '无效群开关' }
      const config = api.config()
      api.setConfig(setGroup(config, group, body.action === 'START'))
      if (body.action === 'END') api.core.hub.leaveTopic(group)
      return { ok: true, enabled: enabled(group), group_id: group }
    })

    api.route('/event', async (req) => {
      if (!check(req)) return denied
      const body = await api.core.http.body(req)
      const event = body.event
      if (!event || typeof event !== 'object') return { ok: false, message: '无效事件' }
      const kind = event.message_type
      const group = event.group_id == null ? '' : String(event.group_id)
      if (group && !enabled(group)) return { ok: true, ignored: 'group disabled' }
      if (String(event.user_id) === String(api.config().botQQ)) return { ok: true, ignored: 'self' }
      if (kind !== 'group' && kind !== 'private' && event.sub_type !== 'poke') return { ok: true, ignored: 'event type' }
      const key = `${kind || 'notice'}:${group || event.user_id}:${event.message_id ?? ''}`
      if (event.message_id != null) {
        if (seen.has(key)) return { ok: true, ignored: 'duplicate' }
        seen.set(key, Date.now())
        for (const [id, at] of seen) if (Date.now() - at > 86400_000) seen.delete(id)
      }
      // 立即应答上报；模型调用和 QQ 发送继续使用原版异步流程。
      Promise.resolve().then(() => event.sub_type === 'poke'
        ? api.core.hub.onPoke(event) : api.core.hub.onMessage(event))
        .catch((error) => api.log.warn('处理 BJGBOT 事件失败：', error.message))
      return { ok: true }
    })

    // 发送前再次检查当前群开关，包括生成中途收到 END 的情形。
    api.on('send', (message, { chatId }) => {
      if (chatId.startsWith('group:') && !enabled(chatId.slice(6))) return null
      return message
    })
    api.route('/health', async (req) => {
      if (!check(req)) return denied
      return { ok: true, groups: api.config().allow.groups, owner, commands_loaded: Boolean(commands),
        memory: Boolean(api.use('memory')) }
    })
    return { enabled, reloadCommands: loadCommands }
  },
}

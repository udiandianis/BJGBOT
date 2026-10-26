import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve, sep } from 'node:path'
import { pathToFileURL } from 'node:url'

const source = resolve(process.env.AURABOT_SOURCE_DIR || '.agent/aurabot')
const load = name => import(pathToFileURL(join(source, 'src', name)))
const temporary = mkdtempSync(join(tmpdir(), 'bjgbot-identity-'))
const originalDataDir = process.env.AURABOT_DATA_DIR
after(() => {
  if (originalDataDir === undefined) delete process.env.AURABOT_DATA_DIR
  else process.env.AURABOT_DATA_DIR = originalDataDir
  assert(resolve(temporary).startsWith(resolve(tmpdir()) + sep))
  rmSync(temporary, { recursive: true, force: true })
})
const { normalize } = await load('core/config.js')
const cfg = () => normalize({ ownerQQ: '10001', botQQ: '10000', dryRun: false,
  allow: { groups: ['1'], private: [] }, model: { provider: 'test', model: 'fake' } })

test('group and private rules identify authorization without a personal relationship', async () => {
  const { rulesText } = await load('persona/personas.js')
  for (const kind of ['social', 'private']) {
    const rules = rulesText(kind, cfg())
    assert(rules.includes('10001'))
    assert(rules.includes('机器人管理权限'))
    assert(!/主人|是你的|私聊里主动一点/.test(rules))
    if (kind === 'social') assert(rules.includes('没有任何电脑操作能力'))
    else assert(rules.includes('可以用手头的工具去做'))
  }
})

test('administrator account retains full private permissions and no group shell access', async () => {
  const { levelFor, checkAllowed, isOwner } = await load('chat/access.js')
  assert.equal(levelFor(cfg(), { kind: 'private', userId: '10001' }), 'full')
  assert.equal(levelFor(cfg(), { kind: 'group', userId: '10001' }), 'social')
  assert.equal(levelFor(cfg(), { kind: 'private', userId: '10002' }), 'social')
  assert.equal(checkAllowed(cfg(), { kind: 'private', userId: '10002' }).allowed, false)
  assert.equal(isOwner(cfg(), '10001'), true)
  assert.equal(isOwner(cfg(), '10002'), false)
})

test('group tool rejects non-administrator requests and executes authorized requests', async () => {
  const { default: module } = await load('modules/group-admin/index.js')
  let builder, context, authorized = false
  const calls = []
  const groupRoles = { peek: () => 'admin', get: async () => 'admin', label: () => '管理员', canManage: () => true }
  module.setup({ config: cfg, context: f => { context = f }, tool: f => { builder = f }, route() {},
    core: { hub: { turnHasOwner: () => authorized }, groupRoles,
      onebot: { call: async (...args) => { calls.push(args); return {} } } } })
  const chat = { kind: 'group', groupId: '1', userId: '10002' }
  const tool = builder({ chat, level: 'social', sessionId: 'test' })
  assert(!/主人/.test(JSON.stringify([tool.description, tool.parameters, context({ chat })])))
  const args = { action: 'ban', user_id: '10002', minutes: 1 }
  assert.equal((await tool.execute(args)).ok, false)
  assert.equal(calls.length, 0)
  authorized = true
  assert.equal((await tool.execute(args)).ok, true)
  assert.equal(calls[0][0], 'set_group_ban')
  assert.equal(calls[0][1].duration, 60)
})

test('administrator status does not amplify emotional responses', async () => {
  const { createMood } = await load('features/companion.js')
  function change(owner, name) {
    process.env.AURABOT_DATA_DIR = join(temporary, name)
    const mood = createMood({ getConfig: cfg })
    const before = mood.current()
    mood.observe('你好可爱', '同一昵称', { direct: true, owner })
    return mood.current() - before
  }
  const ordinary = change(false, 'ordinary')
  const administrator = change(true, 'administrator')
  assert(ordinary > 0)
  assert.equal(administrator, ordinary)
})

test('negative input detection is separate from gentle output guidance', async () => {
  const { scoreText, MOOD_STYLE } = await load('features/companion.js')
  assert(scoreText('垃圾') < 0)
  assert(scoreText('废物') < 0)
  assert(!/垃圾|废物|恶心|怼一句/.test(Object.values(MOOD_STYLE).join(' ')))
  assert(MOOD_STYLE['不太开心'].includes('小委屈'))
})

test('memory profile generation does not seed an administrator relationship', async () => {
  process.env.AURABOT_DATA_DIR = join(temporary, 'memory')
  const { createMemoryStore } = await load('features/memory.js')
  const requests = []
  const dsh = { get: () => null, llm: { async *stream(request) {
    requests.push(request)
    yield { type: 'text-delta', text: '这位群友喜欢喝乌龙茶、参加比赛，也养猫。' }
    yield { type: 'finish', reason: { kind: 'completed' } }
  } } }
  const memory = createMemoryStore({ dsh, getConfig: cfg, hub: {}, log: { info() {}, warn() {}, debug() {} } })
  for (const text of ['这个人更喜欢喝乌龙茶', '这个人周二参加过算法比赛', '这个人养了一只虎斑猫'])
    memory.add({ text, about: '10001', aboutName: '同一昵称', importance: 0.6 })
  assert.equal(await memory.buildProfile('10001'), true)
  const prompt = JSON.stringify(requests[0])
  assert(!/主人|这是你的|她的管理员/.test(prompt))
  assert(prompt.includes('乌龙茶'))
})

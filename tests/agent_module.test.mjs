import test from 'node:test'
import assert from 'node:assert/strict'
import module, { authorised, setGroup } from '../resources/agent/bjgbot/index.mjs'

test('individual group switches preserve every other group and configuration', () => {
  const base = { allow: { groups: ['1'], private: ['9'] }, persona: { current: 'dafeiyu' } }
  const both = setGroup(base, '2', true)
  assert.deepEqual(both.allow.groups, ['1', '2'])
  assert.deepEqual(setGroup(both, '1', false).allow.groups, ['2'])
  assert.deepEqual(base.allow.groups, ['1'])
  assert.deepEqual(both.persona, base.persona)
})

test('HTTP token is required and compared exactly', () => {
  assert.equal(authorised('Bearer correct', 'correct'), true)
  for (const header of ['', 'correct', 'Bearer incorrect']) assert.equal(authorised(header, 'correct'), false)
  assert.equal(authorised('Bearer ', ''), false)
})

function host() {
  let config = { allow: { groups: [], private: [] }, ownerQQ: '10001', botQQ: '10000', modules: {} }
  const routes = new Map(), hooks = new Map(), received = []
  const api = { config: () => config, setConfig: c => { config = c },
    every() {}, rule() {}, on: (name, fn) => hooks.set(name, fn),
    route: (name, fn) => routes.set(name, fn), use: () => ({}),
    core: { http: { body: async req => req.body }, hub: {
      leaveTopic() {}, onMessage: event => received.push(event), onPoke: event => received.push(event),
    } }, log: { warn() {} },
  }
  process.env.BJGBOT_AGENT_TOKEN = 'test-token'
  module.setup(api)
  const call = (name, body) => routes.get(name)({ headers: { authorization: 'Bearer test-token' }, body })
  return { api, call, received, hooks }
}

test('non-owner control is denied, END blocks generation pending delivery', async () => {
  const { call, hooks, api } = host()
  const forbidden = await call('/control', { action: 'START', user_id: 42, group_id: 1 })
  assert.equal(forbidden.ok, false)
  assert.deepEqual(api.config().allow.groups, [])
  await call('/control', { action: 'START', user_id: 10001, group_id: 1 })
  await call('/control', { action: 'START', user_id: 10001, group_id: 2 })
  await call('/control', { action: 'END', user_id: 10001, group_id: 1 })
  assert.equal(hooks.get('send')([], { chatId: 'group:1' }), null)
  assert.deepEqual(hooks.get('send')([], { chatId: 'group:2' }), [])
  assert.deepEqual(api.config().allow.groups, ['2'])
})

test('closed group is not logged or sent to the model, duplicates run once', async () => {
  const { call, received } = host()
  const event = { message_type: 'group', group_id: 1, user_id: 42, message_id: 123, message: 'hello' }
  assert.equal((await call('/event', { event })).ignored, 'group disabled')
  await call('/control', { action: 'START', user_id: 10001, group_id: 1 })
  await call('/event', { event })
  assert.equal((await call('/event', { event })).ignored, 'duplicate')
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(received.length, 1)
})

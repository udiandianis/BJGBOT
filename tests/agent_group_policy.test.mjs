import test from 'node:test'
import assert from 'node:assert/strict'
import { resolve, join } from 'node:path'
import { pathToFileURL } from 'node:url'
const source = resolve(process.env.AURABOT_SOURCE_DIR || '.agent/aurabot')
const { policyFor, decideGroupReply } = await import(pathToFileURL(join(source, 'src/chat/group-policy.js')))
const { normalize } = await import(pathToFileURL(join(source, 'src/core/config.js')))
const now = 10_000_000
function decide(policy = {}, args = {}) {
  return decideGroupReply({ policy: policyFor(policy), now, hour: 12, text: '聊游戏', relevance: 1,
    recentTimes: [now - 2000, now - 1000, now], rand: () => 0,
    ...args })
}

test('zero disables hourly and cooldown limits even after many recent interjections', () => {
  const group = normalize({}).group
  assert.equal(group.cooldownSec, 0)
  assert.equal(group.maxPerHour, 0)
  const times = Array.from({ length: 200 }, (_, i) => now - i * 100)
  assert.equal(decide(group, { interjectTimes: times }).mode, 'interject')
})

test('the base is 30 percent and topic or mood weighting never exceeds 90 percent', () => {
  assert.equal(normalize({}).group.interjectChance, 0.3)
  assert.equal(normalize({}).group.interjectMaxChance, 0.9)
  assert.equal(decide({ minRelevance: 0 }, { relevance: 0, rand: () => 0.299 }).reply, true)
  assert.equal(decide({ minRelevance: 0 }, { relevance: 0, rand: () => 0.3 }).reply, false)
  assert.equal(decide({ interjectChance: 0.3 * 1.5 }, { rand: () => 0.899 }).reply, true)
  assert.equal(decide({ interjectChance: 0.3 * 1.5 }, { rand: () => 0.9 }).reply, false)
})

test('nonzero optional rate settings still work when explicitly configured', () => {
  assert.equal(decide({ maxPerHour: 2 }, { interjectTimes: [now - 30_000, now - 60_000] }).reply, false)
  assert.equal(decide({ cooldownSec: 90 }, { interjectTimes: [now - 30_000] }).reply, false)
})

test('zero disables the burst limit for ordinary mentions, interjections and ongoing conversations', () => {
  const group = normalize({ group: { burstMax: 0 } }).group
  assert.equal(group.burstMax, 0)
  const botReplyTimes = Array(100).fill(now - 1000)
  assert.equal(decide(group, { botReplyTimes, mentioned: true }).mode, 'must')
  assert.equal(decide(group, { botReplyTimes }).mode, 'interject')
  assert.equal(decide(group, { botReplyTimes, engagedUntil: now + 10_000 }).mode, 'engaged')
})

test('quiet hours and relevance still apply, and optional burst limits can be configured explicitly', () => {
  assert.equal(decide({}, { hour: 3 }).reply, false)
  assert.equal(decide({}, { relevance: 0 }).reply, false)
  assert.equal(decide({ burstMax: 8 }, { botReplyTimes: Array(8).fill(now - 1000) }).reply, false)
  assert.equal(decide({}, { mentioned: true, hour: 3 }).mode, 'must')
})

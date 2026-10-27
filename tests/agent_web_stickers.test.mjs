import test, { afterEach } from 'node:test'
import assert from 'node:assert/strict'
import module, { isPreviewUrl, parseImages } from '../resources/agent/web-stickers/index.mjs'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })
const preview = 'https://tse1.mm.bing.net/th?id=OIP.cat&pid=15.1'
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nGQAAAAASUVORK5CYII=', 'base64')
const card = data => '<a class="iusc" m="' + JSON.stringify(data).replaceAll('&', '&amp;').replaceAll('"', '&quot;') + '"></a>'
const html = card({ turl: preview, t: '委屈猫猫', purl: 'https://example.org/meme' })

function host({ sendResult = { message_id: 7 } } = {}) {
  const cfg = { enabled: true, dryRun: false, ownerQQ: '10001', allow: { groups: ['1', '2'], private: [] } }
  let builder
  const sent = [], saved = [], fetched = [], attachments = []
  globalThis.fetch = async (url, options) => {
    fetched.push({ url: String(url), options })
    return String(url).startsWith('https://www.bing.com/images/search')
      ? new Response(html, { headers: { 'content-type': 'text/html' } })
      : new Response(png, { headers: { 'content-type': 'image/png' } })
  }
  module.setup({ config: () => cfg, rule() {}, tool: fn => { builder = fn },
    defineTool: def => ({ ...def, output: {}, execute: async args => {
      try { return await def.execute(args) } catch (error) { return { ok: false, message: error.message } }
    } }),
    dsh: { attachments: { saveImage: async image => {
      attachments.push(image)
      return { attachmentId: 'test-image', mediaType: image.mediaType, bytes: image.data.length, width: 1, height: 1 }
    } } }, log: { debug() {}, warn() {} },
    sendSegments: async (...args) => { sent.push(args); return sendResult },
    use: () => ({ addFromBuffer: async (...args) => { saved.push(args); return { ok: true } }, trim() {} }),
  })
  const tools = id => builder({ chat: { kind: 'group', groupId: id, chatId: 'group:' + id } })
  return { cfg, tools, sent, saved, fetched, attachments, builder: () => builder }
}

test('search metadata cannot provide a local file, internal URL, arbitrary download host or duplicate', () => {
  for (const url of ['file:///etc/passwd', 'http://127.0.0.1/th?id=OIP.x',
    'https://tse1.mm.bing.net.evil.test/th?id=OIP.x', 'https://example.org/x',
    'https://user:secret@tse1.mm.bing.net/th?id=OIP.x', 'https://tse1.mm.bing.net:123/th?id=OIP.x'])
    assert.equal(isPreviewUrl(url), false)
  const bad = card({ turl: 'file:///etc/passwd', t: 'bad' })
  assert.deepEqual(parseImages(bad + html + html).map(x => x.title), ['委屈猫猫'])
})

test('search exposes real image attachments; send delivers bytes to current chat then saves for reuse', async () => {
  const h = host()
  const [search, send] = h.tools('1')
  const found = await search.execute({ query: '委屈猫猫' })
  assert.equal(found.ok, true)
  assert.equal(h.sent.length, 0)
  assert(h.fetched[0].url.includes(encodeURIComponent('委屈猫猫 表情包').replaceAll('%20', '+')))
  assert(h.fetched.every(x => x.options.redirect === 'manual'))
  const blocks = search.output.render({}, found)
  assert.equal(blocks.filter(x => x.type === 'image').length, 1)
  assert.equal(blocks.find(x => x.type === 'image').attachment.attachmentId, 'test-image')
  assert.deepEqual(h.attachments[0].data, png)
  assert.equal((await send.execute({ id: found.results[0].id, name: '委屈猫猫' })).ok, true)
  assert.equal(h.sent[0][0], 'group:1')
  assert.equal(h.sent[0][1][0].data.file, 'base64://' + png.toString('base64'))
  assert.equal(h.saved[0][1].toQQ, false)
})

test('result identifiers cannot cross groups or be replaced with file paths and URLs', async () => {
  const h = host(), [search] = h.tools('1')
  const found = await search.execute({ query: '猫猫' })
  const [, otherSend] = h.tools('2')
  for (const id of [found.results[0].id, '/etc/passwd', preview])
    assert.equal((await otherSend.execute({ id })).ok, false)
  assert.equal(h.sent.length, 0)
  assert.deepEqual(h.builder()({ chat: { kind: 'system' } }), [])
})

test('END during a search prevents later sending; closed chats cannot start searches', async () => {
  const h = host(), [search, send] = h.tools('1')
  const found = await search.execute({ query: '猫猫' })
  h.cfg.allow.groups = []
  assert.equal((await send.execute({ id: found.results[0].id })).ok, false)
  const fetchCount = h.fetched.length
  assert.equal((await search.execute({ query: '猫猫' })).ok, false)
  assert.equal(h.fetched.length, fetchCount)
  assert.equal(h.sent.length, 0)
})

test('failed delivery is not reported as success or saved as a successful send', async () => {
  const h = host({ sendResult: null }), [search, send] = h.tools('1')
  const found = await search.execute({ query: '猫猫' })
  assert.equal((await send.execute({ id: found.results[0].id })).ok, false)
  assert.equal(h.saved.length, 0)
})

test('blocked search and non-image previews return failures without sending anything', async () => {
  const h = host(), [search] = h.tools('1')
  globalThis.fetch = async () => new Response('Unavailable', { status: 503 })
  assert.equal((await search.execute({ query: '猫猫' })).ok, false)
  globalThis.fetch = async url => new Response(String(url).includes('/images/search') ? html : '<html>blocked</html>',
    { headers: { 'content-type': 'text/html' } })
  assert.equal((await search.execute({ query: '猫猫' })).ok, false)
  assert.equal(h.sent.length, 0)
})

test('China Bing redirects work while redirects to arbitrary or internal addresses are blocked before fetching', async () => {
  const h = host(), [search] = h.tools('1')
  const normal = globalThis.fetch
  globalThis.fetch = async (url, options) => String(url).startsWith('https://www.bing.com/')
    ? new Response('', { status: 302, headers: { location: String(url).replace('www.bing.com', 'cn.bing.com') } })
    : String(url).startsWith('https://cn.bing.com/') ? new Response(html) : normal(url, options)
  assert.equal((await search.execute({ query: '猫猫' })).ok, true)
  for (const target of ['http://127.0.0.1/admin', 'https://example.org/file']) {
    let calls = 0
    globalThis.fetch = async () => {
      calls++
      return new Response('', { status: 302, headers: { location: target } })
    }
    assert.equal((await search.execute({ query: '猫猫' })).ok, false)
    assert.equal(calls, 1)
  }
})

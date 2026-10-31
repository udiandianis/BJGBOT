import test, { afterEach } from 'node:test'
import assert from 'node:assert/strict'
import { resolve, join } from 'node:path'
import { pathToFileURL } from 'node:url'

const source=resolve(process.env.AURABOT_SOURCE_DIR || '.agent/aurabot')
const {default:module}=await import(pathToFileURL(join(source,'src/modules/imagegen/index.js')))
const originalFetch=globalThis.fetch
afterEach(()=>{globalThis.fetch=originalFetch})

function host({authorized=true,sent={message_id:1},enabled=true,ownerOnly=true}={}) {
  let builder,calls=0
  const deliveries=[],memories=[]
  const config={allow:{groups:['1']},imageGen:{enabled,baseUrl:'https://example.invalid/v1',model:'test-image',ownerOnly,size:'1024x1024',stylePrompt:''}}
  globalThis.fetch=async()=>{
    calls++
    return new Response(JSON.stringify({data:[{b64_json:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nGQAAAAASUVORK5CYII='}]}),{headers:{'content-type':'application/json'}})
  }
  module.setup({config:()=>config,log:{info(){}},lazy:()=>({addEvent:e=>memories.push(e)}),
    core:{local:{active:()=>false},hub:{turnSendersAllOwner:()=>authorized,
      sendSegments:async(...args)=>{deliveries.push(args);return sent}}},tool:fn=>{builder=fn}})
  const tool=builder({chat:{kind:'group',chatId:'group:1'},sessionId:'test'})
  return {tool,deliveries,memories,config,calls:()=>calls}
}
test('native image tool is hidden until a provider is enabled',()=>{
  assert.deepEqual(host({enabled:false}).tool,[])
})
test('native administrator setting rejects unauthorized generation before calling the provider',async()=>{
  const h=host({authorized:false})
  assert.equal((await h.tool.execute({prompt:'a whale'})).ok,false)
  assert.equal(h.calls(),0)
})

test('ordinary group members can generate and send images when ownerOnly is disabled',async()=>{
  const h=host({authorized:false,ownerOnly:false})
  assert.equal((await h.tool.execute({prompt:'a whale'})).ok,true)
  assert.equal(h.calls(),1)
  assert.equal(h.deliveries[0][0],'group:1')
  assert.equal(h.deliveries[0][1][0].type,'image')
})
test('generation followed by a failed QQ send returns failure and does not record a successful event',async()=>{
  const h=host({sent:null})
  assert.equal((await h.tool.execute({prompt:'a whale'})).ok,false)
  assert.equal(h.deliveries.length,1)
  assert.equal(h.memories.length,0)
})
test('native image tool delivers image bytes to the current chat and records success after delivery',async()=>{
  const h=host()
  assert.equal((await h.tool.execute({prompt:'a whale'})).ok,true)
  assert.equal(h.deliveries[0][0],'group:1')
  assert.equal(h.deliveries[0][1][0].type,'image')
  assert.equal(h.memories.length,1)
})

test('image generation and delivery run one job at a time without dropping queued requests',async()=>{
  const h=host(),png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nGQAAAAASUVORK5CYII='
  let release,requests=0
  const gate=new Promise(resolve=>{release=resolve})
  globalThis.fetch=async()=>{requests++;if(requests===1)await gate;return new Response(JSON.stringify({data:[{b64_json:png}]}))}
  const first=h.tool.execute({prompt:'first whale'}),second=h.tool.execute({prompt:'second whale'})
  await new Promise(resolve=>setImmediate(resolve))
  assert.equal(requests,1)
  release()
  const results=await Promise.all([first,second])
  assert(results.every(result=>result.ok))
  assert.equal(requests,2);assert.equal(h.deliveries.length,2)
})

test('closing a group cancels its queued generation before another provider request',async()=>{
  const h=host(),png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nGQAAAAASUVORK5CYII='
  let release,requests=0
  const gate=new Promise(resolve=>{release=resolve})
  globalThis.fetch=async()=>{requests++;await gate;return new Response(JSON.stringify({data:[{b64_json:png}]}))}
  const first=h.tool.execute({prompt:'first whale'}),second=h.tool.execute({prompt:'second whale'})
  await new Promise(resolve=>setImmediate(resolve))
  h.config.allow.groups=[];release()
  await first
  assert.equal((await second).ok,false)
  assert.equal(requests,1)
})

test('a failed image job does not block the next queued request',async()=>{
  const h=host(),png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nGQAAAAASUVORK5CYII='
  let requests=0
  globalThis.fetch=async()=>++requests===1?new Response('{}',{status:503}):new Response(JSON.stringify({data:[{b64_json:png}]}))
  const results=await Promise.allSettled([h.tool.execute({prompt:'first whale'}),h.tool.execute({prompt:'second whale'})])
  assert.equal(results[0].status,'fulfilled');assert.equal(results[0].value.ok,false)
  assert.equal(results[1].status,'fulfilled');assert.equal(results[1].value.ok,true)
  assert.equal(h.deliveries.length,1)
})

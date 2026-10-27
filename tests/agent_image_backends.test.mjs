import test, { afterEach } from 'node:test'
import assert from 'node:assert/strict'
import { resolve, join } from 'node:path'
import { pathToFileURL } from 'node:url'
const source=resolve(process.env.AURABOT_SOURCE_DIR || '.agent/aurabot')
const {createImageGen}=await import(pathToFileURL(join(source,'src/features/imagegen.js')))
const {normalize,publicConfig,mergeFromPanel}=await import(pathToFileURL(join(source,'src/core/config.js')))
const originalFetch=globalThis.fetch
afterEach(()=>{globalThis.fetch=originalFetch})
const png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nGQAAAAASUVORK5CYII='
const gemini=()=>new Response(JSON.stringify({candidates:[{content:{parts:[{thought:true,inlineData:{mimeType:'image/png',data:'invalid'}},
  {inlineData:{mimeType:'image/png',data:png}}]}}]}))
const openai=()=>new Response(JSON.stringify({data:[{b64_json:png}]}))
const fail=()=>new Response(JSON.stringify({error:{message:'service unavailable'}}),{status:503})
function config(){return normalize({imageGen:{enabled:true,provider:'gemini',model:'pro',baseUrl:'https://gemini.invalid/v1beta',apiKey:'primary-secret',
  size:'768x1024',stylePrompt:'柔和',fallbacks:[
    {provider:'gemini',model:'flash',baseUrl:'https://gemini.invalid/v1beta',apiKey:'flash-secret'},
    {provider:'openai',model:'grok',baseUrl:'https://grok.invalid/v1',apiKey:'grok-secret'}]}})}
function generator(c=config()){return createImageGen({getConfig:()=>c,log:{info(){},warn(){}},local:{active:()=>false}})}

test('Gemini returns the final image, preserves the prompt and stops after primary success',async()=>{
  const calls=[];globalThis.fetch=async(url,o)=>{calls.push([url,JSON.parse(o.body)]);return gemini()}
  assert.deepEqual(await generator().generate('蓝鲸'),Buffer.from(png,'base64'))
  assert.equal(calls.length,1)
  assert(calls[0][0].endsWith('/models/pro:generateContent'))
  assert.equal(calls[0][1].contents[0].parts[0].text,'柔和，蓝鲸')
  assert.equal(calls[0][1].generationConfig.imageConfig.aspectRatio,'3:4')
})
test('primary failure switches to Flash without calling Grok',async()=>{
  const urls=[];globalThis.fetch=async url=>{urls.push(url);return urls.length===1?fail():gemini()}
  await generator().generate('蓝鲸')
  assert.equal(urls.length,2)
  assert(urls[0].includes('/pro:'));assert(urls[1].includes('/flash:'))
})
test('a timeout then a non-image result switches to the OpenAI-compatible Grok backend',async()=>{
  const calls=[];globalThis.fetch=async(url,o)=>{
    calls.push([url,JSON.parse(o.body)])
    if(calls.length===1)throw new DOMException('timed out','TimeoutError')
    if(calls.length===2)return new Response(JSON.stringify({candidates:[{content:{parts:[{text:'no picture'}]}}]}))
    return openai()
  }
  await generator().generate('蓝鲸')
  assert.equal(calls.length,3)
  assert(calls[2][0].endsWith('/images/generations'))
  assert.equal(calls[2][1].model,'grok')
})
test('invalid image bytes trigger a fallback, while all failures return a generic tool error',async()=>{
  let count=0
  globalThis.fetch=async()=>{count++;return count===1?new Response(JSON.stringify({candidates:[{content:{parts:[{inlineData:{mimeType:'image/png',data:'broken'}}]}}]})):gemini()}
  await generator().generate('蓝鲸');assert.equal(count,2)
  count=0;globalThis.fetch=async()=>{count++;return fail()}
  await assert.rejects(generator().generate('蓝鲸'),/没有生成可发送的图片/)
  assert.equal(count,3)
})
test('an explicit provider content refusal stops rather than routing around the refusal',async()=>{
  let count=0;globalThis.fetch=async()=>{count++;return new Response(JSON.stringify({promptFeedback:{blockReason:'SAFETY'}}))}
  await assert.rejects(generator().generate('test'),/没有生成可发送的图片/)
  assert.equal(count,1)
})
test('all provider keys are hidden from the panel and survive ordinary saves and reordering',()=>{
  const c=config(),visible=publicConfig(c)
  for(const key of ['primary-secret','flash-secret','grok-secret'])assert(!JSON.stringify(visible).includes(key))
  assert.equal(visible.imageGen.fallbacks[1].apiKeySet,true)
  assert.equal(mergeFromPanel(c,visible).imageGen.fallbacks[1].apiKey,'grok-secret')
  visible.imageGen.fallbacks.reverse()
  const saved=mergeFromPanel(c,visible)
  assert.equal(saved.imageGen.fallbacks[0].model,'grok')
  assert.equal(saved.imageGen.fallbacks[0].apiKey,'grok-secret')
  assert.equal(saved.imageGen.fallbacks[1].apiKey,'flash-secret')
})

import test, { afterEach } from 'node:test'
import assert from 'node:assert/strict'
import module from '../resources/agent/vision-assist/index.mjs'
const originalFetch=globalThis.fetch
afterEach(()=>{globalThis.fetch=originalFetch})
const picture={type:'image',mediaType:'image/png',data:'test-image-bytes'}
const observed=(uncertain=false)=>({description:'画面中是一个背着刀的黑白漫画人物',character:uncertain?'':'虚构角色A',uncertain})
const gemini=value=>new Response(JSON.stringify({candidates:[{content:{parts:[{text:JSON.stringify(value)}]}}]}))
const grok=value=>new Response(JSON.stringify({choices:[{message:{content:JSON.stringify(value)}}]}))
function host(){
  const hooks=new Map();let build,context
  const cfg={enabled:true,ownerQQ:'10001',allow:{groups:['1','2'],private:[]},imageGen:{provider:'gemini',baseUrl:'https://gemini.invalid/v1beta',apiKey:'gemini-secret',
    fallbacks:[{provider:'openai',baseUrl:'https://grok.invalid/v1',apiKey:'grok-secret'}]}}
  module.setup({config:()=>cfg,settings:()=>module.defaults,on:(n,fn)=>hooks.set(n,fn),context:fn=>{context=fn},tool:fn=>{build=fn},
    defineTool:def=>def,log:{warn(){}}})
  const chat=id=>({kind:'group',groupId:id,chatId:'group:'+id})
  return {cfg,feed:(id,content=[picture])=>hooks.get('prompt')(content,{chat:chat(id),queryText:'你认识这个吗'}),
    tool:id=>build({chat:chat(id)}),context:id=>context({chat:chat(id)})}
}
test('certain Gemini observations return to the chat model without calling Grok or sending a fixed reply',async()=>{
  const h=host();h.feed('1');const calls=[]
  globalThis.fetch=async(url,o)=>{calls.push([url,JSON.parse(o.body)]);return gemini(observed())}
  const r=await h.tool('1').execute({})
  assert.equal(r.ok,true);assert.equal(r.observations.length,1);assert.equal(calls.length,1)
  assert.equal(calls[0][1].contents[0].parts[1].inlineData.data,picture.data)
  assert(h.context('1').includes('qq_inspect_image'))
})
test('uncertain Gemini observations are cross-checked by Grok',async()=>{
  const h=host();h.feed('1');const calls=[]
  globalThis.fetch=async(url,o)=>{calls.push([url,JSON.parse(o.body)]);return calls.length===1?gemini(observed(true)):grok(observed())}
  const r=await h.tool('1').execute({question:'核实漫画人物'})
  assert.equal(r.observations.length,2)
  assert(calls[1][0].endsWith('/chat/completions'))
  assert(calls[1][1].messages[1].content[1].image_url.url.includes(picture.data))
})
test('Gemini transport failure also falls back to Grok',async()=>{
  const h=host();h.feed('1');let calls=0
  globalThis.fetch=async()=>{calls++;if(calls===1)throw new Error('offline');return grok(observed())}
  assert.equal((await h.tool('1').execute({})).ok,true);assert.equal(calls,2)
})
test('images and analysis remain within the originating chat; closed groups cannot call helpers',async()=>{
  const h=host();h.feed('1');let calls=0;globalThis.fetch=async()=>{calls++;return gemini(observed())}
  assert.equal((await h.tool('2').execute({})).ok,false)
  h.cfg.allow.groups=[]
  assert.equal((await h.tool('1').execute({})).ok,false)
  assert.equal(calls,0);assert.equal(h.context('2'),'')
})
test('invalid picture numbers and missing attachments never cause a model request',async()=>{
  const h=host();let calls=0;globalThis.fetch=async()=>{calls++;return gemini(observed())}
  assert.equal((await h.tool('1').execute({})).ok,false)
  h.feed('1')
  for(const image_index of [0,-1,2,1.5])assert.equal((await h.tool('1').execute({image_index})).ok,false)
  assert.equal(calls,0)
})
test('when both services fail only a tool failure is returned for Dafeiyu to explain',async()=>{
  const h=host();h.feed('1');let calls=0
  globalThis.fetch=async()=>{calls++;throw new Error('private technical error')}
  const r=await h.tool('1').execute({})
  assert.equal(r.ok,false);assert.equal(calls,2)
  assert(!JSON.stringify(r).includes('private technical error'))
})

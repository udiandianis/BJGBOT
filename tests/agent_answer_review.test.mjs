import test,{afterEach} from 'node:test'
import assert from 'node:assert/strict'
import module from '../resources/agent/answer-review/index.mjs'
const originalFetch=globalThis.fetch
afterEach(()=>{globalThis.fetch=originalFetch})
const gemini=value=>new Response(JSON.stringify({candidates:[{content:{parts:[{text:JSON.stringify(value)}]}}]}))
const grok=value=>new Response(JSON.stringify({choices:[{message:{content:JSON.stringify(value)}}]}))
function host(){
 let build,rule
 const cfg={enabled:true,ownerQQ:'10001',allow:{groups:['1'],private:[]},imageGen:{provider:'gemini',baseUrl:'https://gemini.invalid/v1beta',apiKey:'gemini-secret',
   fallbacks:[{provider:'openai',baseUrl:'https://grok.invalid/v1',apiKey:'grok-secret'}]}}
 module.setup({config:()=>cfg,settings:()=>module.defaults,rule:fn=>{rule=fn},tool:fn=>{build=fn},defineTool:def=>def,log:{warn(){}}})
 const chat={kind:'group',groupId:'1',chatId:'group:1'}
 return {cfg,chat,rule:()=>rule(),tool:()=>build({chat})}
}

test('both reviewers receive only the original problem independently and no reply is sent automatically',async()=>{
 const h=host(),calls=[]
 globalThis.fetch=async(url,o)=>{calls.push([url,JSON.parse(o.body)]);return calls.length===1?gemini({answer:'1/7',checks:['代入验证'],uncertain:false}):grok({answer:'1/7',checks:['条件概率'],uncertain:false})}
 const r=await h.tool().execute({question:'原题：条件概率问题'})
 assert.equal(r.ok,true);assert.equal(r.complete,true);assert.equal(r.reviews.length,2)
 assert.equal(calls[0][1].contents[0].parts[0].text,'原题：条件概率问题')
 assert.equal(calls[1][1].messages[1].content,'原题：条件概率问题')
 assert.equal(calls[1][1].reasoning_effort,'high')
 assert(h.rule().includes('最终回答前调用 qq_verify_answer'))
})

test('disagreement and uncertainty are retained for DeepSeek to verify rather than resolved by voting',async()=>{
 const h=host();let calls=0
 globalThis.fetch=async()=>++calls===1?gemini({answer:'1/4',checks:[],uncertain:false}):grok({answer:'1/7',checks:['分母是至少一红'],uncertain:true})
 const r=await h.tool().execute({question:'题目'})
 assert.deepEqual(r.reviews.map(x=>x.answer),['1/4','1/7'])
 assert.equal(r.reviews[1].uncertain,true)
 assert(h.rule().includes('不以多数票'))
})

test('one unavailable provider returns partial completion without claiming a double check',async()=>{
 const h=host();let calls=0
 globalThis.fetch=async()=>{if(++calls===1)throw new Error('private failure');return grok({answer:'42',uncertain:false})}
 const r=await h.tool().execute({question:'题目'})
 assert.equal(calls,2);assert.equal(r.ok,true);assert.equal(r.complete,false)
 assert.deepEqual(r.failed_models,['gemini-3.8-flash-high'])
 assert(!JSON.stringify(r).includes('private failure'))
})

test('closed groups, non-whitelisted private chats and empty questions make no provider requests',async()=>{
 const h=host();let calls=0;globalThis.fetch=async()=>{calls++;return gemini({answer:'0'})}
 assert.equal((await h.tool().execute({question:' '})).ok,false)
 const tool=h.tool();h.cfg.allow.groups=[]
 assert.equal((await tool.execute({question:'题目'})).ok,false)
 assert.deepEqual(h.tool(),[])
 h.chat.kind='private';h.chat.userId='10002'
 assert.deepEqual(h.tool(),[])
 assert.equal(calls,0)
})

test('a group disabled between reviews stops the second request',async()=>{
 const h=host();let calls=0
 globalThis.fetch=async()=>{calls++;h.cfg.allow.groups=[];return gemini({answer:'0',uncertain:false})}
 const r=await h.tool().execute({question:'题目'})
 assert.equal(r.ok,false);assert.equal(calls,1)
})

test('all failures return a natural-response fact without leaking provider errors or credentials',async()=>{
 const h=host();globalThis.fetch=async()=>new Response('private-key-error',{status:503})
 const r=await h.tool().execute({question:'题目'})
 assert.equal(r.ok,false);assert.equal(r.complete,false)
 assert.equal(r.failed_models.length,2)
 for(const text of ['gemini-secret','grok-secret','private-key-error'])assert(!JSON.stringify(r).includes(text))
})

import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve, sep } from 'node:path'
import { pathToFileURL } from 'node:url'

const temporary=mkdtempSync(join(tmpdir(),'bjgbot-image-context-'))
const previous={data:process.env.AURABOT_DATA_DIR,workspace:process.env.AURABOT_WORKSPACE}
process.env.AURABOT_DATA_DIR=temporary
process.env.AURABOT_WORKSPACE=join(temporary,'workspace')
after(()=>{
  for(const [name,value] of [['AURABOT_DATA_DIR',previous.data],['AURABOT_WORKSPACE',previous.workspace]])
    if(value===undefined)delete process.env[name];else process.env[name]=value
  assert(resolve(temporary).startsWith(resolve(tmpdir())+sep))
  rmSync(temporary,{recursive:true,force:true})
})
const source=resolve(process.env.AURABOT_SOURCE_DIR || '.agent/aurabot')
const load=name=>import(pathToFileURL(join(source,name)))
const {normalize}=await load('src/core/config.js')
const {createHub}=await load('src/chat/hub.js')
const {createFakeDsh}=await load('test/helpers/fake-dsh.js')
const image={type:'image',data:{file:'base64://iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nGQAAAAASUVORK5CYII='}}
const at={type:'at',data:{qq:'10000'}}
const event=(group,id,message)=>({post_type:'message',message_type:'group',group_id:group,user_id:10001,
  self_id:10000,message_id:id,sender:{nickname:'测试昵称'},message})

async function scenario(run,{quotedGroup=1,quoteFails=false}={}) {
  process.env.AURABOT_DATA_DIR=join(temporary,Math.random().toString(36).slice(2))
  const cfg=normalize({enabled:true,botQQ:'10000',ownerQQ:'10001',allow:{groups:['1','2'],private:[]},
    voice:{autoChance:0},stickers:{autoChance:0},merge:{enabled:false},model:{provider:'test',model:'fake'}})
  const fake=createFakeDsh({brain:async()=> '[沉默]'})
  const hub=createHub({dsh:fake.ctx,getConfig:()=>cfg,log:{info(){},debug(){},warn(){},error(){}},
    onebot:{call:async action=>{
      if(action==='get_msg') {
        if(quoteFails)throw new Error('message unavailable')
        return event(quotedGroup,9,[image])
      }
      return {group_name:'测试群'}
    }},stickers:{},tts:{},buildTools:()=>[],contextProviders:[],
    hooks:{groupDecide:(_decision,{msg})=>({reply:msg.mentioned,mode:'must'})}})
  fake.ctx.on('session/event',(session,e)=>hub.onSessionEvent(session,e))
  const turn=async()=>{
    const end=Date.now()+3000
    while(!fake.turns.length && Date.now()<end)await new Promise(r=>setTimeout(r,10))
    assert.equal(fake.turns.length,1)
    return fake.turns[0]
  }
  try {await run({hub,fake,turn})} finally {fake.dispose()}
}

test('replying to a picture passes the actual image to the model',async()=>scenario(async({hub,turn})=>{
  await hub.onMessage(event(1,10,[{type:'reply',data:{id:'9'}},at,{type:'text',data:{text:'这张图是什么'}}]))
  assert.equal((await turn()).images,1)
}))
test('a picture sent before a separate mention is retained even when the picture did not trigger a reply',async()=>scenario(async({hub,fake,turn})=>{
  await hub.onMessage(event(1,1,[image]))
  assert.equal(fake.turns.length,0)
  await hub.onMessage(event(1,2,[at,{type:'text',data:{text:'看看刚才的图'}}]))
  assert.equal((await turn()).images,1)
}))
test('pictures from another group never enter the current group context',async()=>scenario(async({hub,turn})=>{
  await hub.onMessage(event(1,1,[image]))
  await hub.onMessage(event(2,2,[at]))
  assert.equal((await turn()).images,0)
}))
test('a forged reference to another chat is not used to fetch its pictures',async()=>scenario(async({hub,turn})=>{
  await hub.onMessage(event(1,10,[{type:'reply',data:{id:'9'}},at]))
  assert.equal((await turn()).images,0)
},{quotedGroup:2}))
test('inline pictures are not duplicated by the recent-message buffer',async()=>scenario(async({hub,turn})=>{
  await hub.onMessage(event(1,1,[at,image]))
  assert.equal((await turn()).images,1)
}))
test('unavailable quoted messages do not prevent the text request from completing',async()=>scenario(async({hub,turn})=>{
  await hub.onMessage(event(1,10,[{type:'reply',data:{id:'9'}},at]))
  assert.equal((await turn()).images,0)
},{quoteFails:true}))

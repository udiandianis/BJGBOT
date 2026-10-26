import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve, sep } from 'node:path'
import { pathToFileURL } from 'node:url'

const source=resolve(process.env.AURABOT_SOURCE_DIR || '.agent/aurabot')
const load=name=>import(pathToFileURL(join(source,name)))

test('bare group mention reaches the model without being labeled an image', async () => {
  const temporary=mkdtempSync(join(tmpdir(),'bjgbot-empty-message-'))
  const previous={data:process.env.AURABOT_DATA_DIR,workspace:process.env.AURABOT_WORKSPACE}
  process.env.AURABOT_DATA_DIR=temporary
  process.env.AURABOT_WORKSPACE=join(temporary,'workspace')
  let fake
  try {
    const {normalize}=await load('src/core/config.js')
    const {createHub}=await load('src/chat/hub.js')
    const {createFakeDsh}=await load('test/helpers/fake-dsh.js')
    const cfg=normalize({enabled:true,botQQ:'10000',ownerQQ:'10001',allow:{groups:['1'],private:[]},
      voice:{autoChance:0},stickers:{autoChance:0},
      merge:{groupWaitSec:.2,groupMaxSec:1},model:{provider:'test',model:'fake'}})
    fake=createFakeDsh({brain:async()=> '在呢'})
    const hub=createHub({dsh:fake.ctx,getConfig:()=>cfg,log:{info(){},debug(){},warn(){}},
      onebot:{call:async()=>({group_name:'测试群'})},stickers:{},tts:{},buildTools:()=>[],contextProviders:[]})
    fake.ctx.on('session/event',(session,event)=>hub.onSessionEvent(session,event))
    await hub.onMessage({post_type:'message',message_type:'group',group_id:1,user_id:10001,
      message_id:1,self_id:10000,sender:{nickname:'测试昵称'},message:[
        {type:'at',data:{qq:'10000'}},{type:'text',data:{text:' '}}]})
    const end=Date.now()+5000
    while(!fake.turns.length && Date.now()<end) await new Promise(r=>setTimeout(r,25))
    assert.equal(fake.turns.length,1)
    assert(fake.turns[0].userText.includes('没有正文'))
    assert(!fake.turns[0].userText.includes('图片/表情'))
    assert.equal(fake.turns[0].images,0)
  } finally {
    fake?.dispose()
    if(previous.data===undefined) delete process.env.AURABOT_DATA_DIR
    else process.env.AURABOT_DATA_DIR=previous.data
    if(previous.workspace===undefined) delete process.env.AURABOT_WORKSPACE
    else process.env.AURABOT_WORKSPACE=previous.workspace
    assert(resolve(temporary).startsWith(resolve(tmpdir())+sep))
    rmSync(temporary,{recursive:true,force:true})
  }
})

test('actual image segments retain their image marker and attachment',async()=>{
  const {parseMessageEvent}=await load('src/chat/inbound.js')
  const message=parseMessageEvent({message_type:'group',group_id:1,user_id:10001,
    message:[{type:'image',data:{url:'https://example.invalid/picture.png'}}]},'10000')
  assert(message.text.includes('[图片]'))
  assert.equal(message.images.length,1)
})

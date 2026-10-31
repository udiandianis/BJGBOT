import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { once } from 'node:events'
import { createHash } from 'node:crypto'
import { mkdtemp, mkdir, readFile, writeFile, symlink, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { resolve, join, dirname, basename } from 'node:path'
import { pathToFileURL } from 'node:url'

const root=resolve('.'),received=[]
let stage,upstream,gateway,url,configuration
before(async()=>{
  stage=await mkdtemp(join(tmpdir(),'bjgbot-gateway-test-'))
  upstream=createServer(async(req,res)=>{
    const hash=createHash('sha256');let bytes=0
    for await(const chunk of req){hash.update(chunk);bytes+=chunk.length}
    received.push({path:req.url,authorization:req.headers.authorization,hash:hash.digest('hex'),bytes})
    res.setHeader('content-type','application/json')
    res.end(JSON.stringify({retcode:0,status:'ok',data:{message_id:123}}))
  })
  upstream.listen(0,'127.0.0.1');await once(upstream,'listening')
  for(const directory of ['scripts','config','.agent/host','.agent/home/plugins-data/aurabot','resources/agent/bjgbot'])
    await mkdir(join(stage,directory),{recursive:true})
  await symlink(join(root,'.agent/host/node_modules'),join(stage,'.agent/host/node_modules'),'dir')
  await writeFile(join(stage,'.agent/host/package.json'),'{}')
  await writeFile(join(stage,'config/bot_settings.json'),JSON.stringify({agent:{token:'relay-test-token'},bot:{qq:10000},
    napcat:{api_url:`http://127.0.0.1:${upstream.address().port}`,api_token:'upstream-test-token'}}))
  configuration=join(stage,'.agent/home/plugins-data/aurabot/config.json')
  await writeFile(configuration,JSON.stringify({allow:{groups:['1']}}))
  await writeFile(join(stage,'resources/agent/bjgbot/index.mjs'),await readFile(join(root,'resources/agent/bjgbot/index.mjs')))
  const script=(await readFile(join(root,'scripts/agent_gateway.mjs'),'utf8')).replace("server.listen(5030,",'server.listen(0,')
  await writeFile(join(stage,'scripts/agent_gateway.mjs'),script)
  ;({server:gateway}=await import(pathToFileURL(join(stage,'scripts/agent_gateway.mjs'))))
  if(!gateway.listening)await once(gateway,'listening')
  url=`http://127.0.0.1:${gateway.address().port}/onebot/send_group_msg`
})
after(async()=>{
  for(const server of [gateway,upstream])if(server){server.closeAllConnections();await new Promise(resolve=>server.close(resolve))}
  if(stage){assert.equal(dirname(stage),resolve(tmpdir()));assert(basename(stage).startsWith('bjgbot-gateway-test-'));await rm(stage,{recursive:true,force:true})}
})
function send(body,token='relay-test-token'){
  return fetch(url,{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+token},body})
}

test('relay forwards the original large image JSON bytes without rebuilding the payload',async()=>{
  const body=' { "group_id" : 1, "message" : [{"type":"image","data":{"file":"base64://'+'a'.repeat(12*1024*1024)+'"}}] } '
  const response=await send(body)
  assert.equal((await response.json()).data.message_id,123)
  assert.equal(received.at(-1).hash,createHash('sha256').update(body).digest('hex'))
  assert.equal(received.at(-1).bytes,Buffer.byteLength(body))
  assert.equal(received.at(-1).authorization,'Bearer upstream-test-token')
})

test('relay still rejects invalid credentials and disabled groups before forwarding',async()=>{
  const before=received.length
  assert.equal((await send('{"group_id":1}','wrong-token')).status,401)
  assert.equal((await (await send('{"group_id":2}')).json()).retcode,1403)
  assert.equal(received.length,before)
})

test('a group switch is observed immediately on the next relay request',async()=>{
  const before=received.length
  await writeFile(configuration,JSON.stringify({allow:{groups:[]}}))
  assert.equal((await (await send('{"group_id":1}')).json()).retcode,1403)
  assert.equal(received.length,before)
})

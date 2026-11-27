import assert from 'node:assert/strict';
import {test} from 'node:test';
import worker from './worker.mjs';

const env = {VERA_SITE_OWNER_ID:'sample-owner', VERA_WORK_TOKEN:'sample-source-token'};
function call(method, params, identity = 'sample-owner') {
  const headers = {'Content-Type':'application/json'};
  if (identity) headers['oai-authenticated-user-id'] = identity;
  return worker.fetch(new Request('https://site.example/mcp', {
    method:'POST',headers,body:JSON.stringify({jsonrpc:'2.0',id:1,method,params})
  }), env);
}

test('Site discovery exposes scoped tools and blocks other identities', async () => {
  const discovery = await (await call('server/discover')).json();
  assert.deepEqual(discovery.result.supportedVersions,['2026-07-28']);
  const listing = await (await call('tools/list')).json();
  assert.equal(listing.result.tools.length,9);
  const denied = await (await call('tools/call',{name:'list_tasks'},'other-owner')).json();
  assert.equal(denied.result.isError,true);
  const absent = await (await call('tools/call',{name:'read_results'},null)).json();
  assert.equal(absent.result.isError,true);
});

test('Two scheduled-style reads resume from the persisted consumer cursor', async t => {
  const fetch = t.mock.method(globalThis,'fetch',async (url, req) => {
    assert.equal(new URL(url).origin,'https://publish-task.onrender.com');
    assert.equal(req.redirect,'error');
    assert.equal(req.headers.Authorization,'Bearer '+env.VERA_WORK_TOKEN);
    const cursor = Number(new URL(url).searchParams.get('after'));
    return Response.json(cursor === 0 ? {
      results:[{cursor:7, source_id:'demo:1', decisions:['確認日期']}],next_cursor:7
    } : {results:[],next_cursor:7});
  });
  const read = async after => {
    const response = await (await call('tools/call',{name:'read_results',arguments:{after}})).json();
    return JSON.parse(response.result.content[0].text);
  };
  const first = await read(0);
  const stored = JSON.parse(JSON.stringify({after:first.next_cursor}));
  assert.equal(first.results.length,1);
  assert.deepEqual((await read(stored.after)).results,[]);
  assert.equal(fetch.mock.callCount(),2);
});

test('Hosted bridge separates reading work from persisting a completed cursor',async t=>{
  const seen=[];
  t.mock.method(globalThis,'fetch',async(url,request)=>{
    seen.push([new URL(url).pathname,request.method,request.body]);
    return Response.json({acknowledged:request.method==='PUT'?8:0});
  });
  const invoke=async(name,args)=>(await (await call('tools/call',{name,arguments:args})).json()).result;
  const read=await invoke('resume_work',{consumer:'vera-qa'});
  assert.equal(JSON.parse(read.content[0].text).acknowledged,0);
  const completed=await invoke('ack_results',{consumer:'vera-qa',after:0,cursors:[8]});
  assert.equal(JSON.parse(completed.content[0].text).acknowledged,8);
  assert.deepEqual(seen,[['/api/v1/work/inbox/vera-qa','GET',undefined],
    ['/api/v1/work/inbox/vera-qa','PUT','{"after":0,"cursors":[8]}']]);
  assert.equal((await invoke('resume_work',{consumer:'https://invalid.example'})).isError,true);
});

test('Automatic call requests route only to source-authorized scheduling and do not carry device credentials', async t => {
  const task_id='c21a6a0f-2a0d-4c13-9b12-010000000001';
  const fetch=t.mock.method(globalThis,'fetch',async(url,req)=>{
    assert.equal(new URL(url).pathname,'/api/v1/work/tasks/'+task_id+'/call');
    assert.equal(req.method,'POST');
    assert.deepEqual(JSON.parse(req.body),{due_at:1900000000});
    return Response.json({error:'Owner consent required'},{status:403});
  });
  const result=(await (await call('tools/call',{name:'schedule_task_call',arguments:{task_id,due_at:1900000000,device_id:'ignored'}})).json()).result;
  assert.equal(result.isError,true);
  assert.equal(fetch.mock.callCount(),1);
});

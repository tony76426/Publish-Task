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

test('request_call uses the scoped route and no caller-supplied device or return permission',async t=>{
  const task_id='12345678-1234-4234-8234-123456789abc';
  t.mock.method(globalThis,'fetch',async(url,req)=>{
    assert.equal(new URL(url).pathname,'/api/v1/work/tasks/'+task_id+'/request-call');
    assert.equal(req.method,'POST');
    assert.deepEqual(JSON.parse(req.body),{due_at:1800000000});
    return Response.json({state:'queued'});
  });
  const response=await (await call('tools/call',{name:'request_call',arguments:{task_id,due_at:1800000000}})).json();
  assert.equal(JSON.parse(response.result.content[0].text).state,'queued');
});

test('network failures are categorized without exposing raw connection errors', async t => {
  t.mock.method(globalThis,'fetch',async () => {
    throw new TypeError('Bearer private-secret: fetch failed');
  });
  const result = await (await call('tools/call',{name:'list_tasks',arguments:{}})).json();
  const message = result.result.content[0].text;
  assert.equal(result.result.isError,true);
  assert.match(message,/網路連線或重新導向失敗/);
  assert.doesNotMatch(message,/private-secret|Bearer/);
});

test('fetch timeouts are distinguished from network failures', async t => {
  t.mock.method(globalThis,'fetch',async () => {
    const error = new Error('secret details');
    error.name = 'TimeoutError';
    throw error;
  });
  const result = await (await call('tools/call',{name:'list_tasks',arguments:{}})).json();
  assert.equal(result.result.isError,true);
  assert.match(result.result.content[0].text,/連線逾時（12 秒）/);
  assert.doesNotMatch(result.result.content[0].text,/secret details/);
});

test('unexpected JSON is distinct from HTTP error status', async t => {
  t.mock.method(globalThis,'fetch',async () => new Response('not-json',{status:200}));
  const result = await (await call('tools/call',{name:'list_tasks',arguments:{}})).json();
  assert.equal(result.result.isError,true);
  assert.match(result.result.content[0].text,/回應解析失敗（HTTP 200）/);
});

test('upstream HTTP status remains visible without response body', async t => {
  t.mock.method(globalThis,'fetch',async () => Response.json({error:'private details'},{status:503}));
  const result = await (await call('tools/call',{name:'list_tasks',arguments:{}})).json();
  assert.equal(result.result.isError,true);
  assert.equal(result.result.content[0].text,'VERA 工作 API 回傳 HTTP 503');
  assert.doesNotMatch(result.result.content[0].text,/private details/);
});

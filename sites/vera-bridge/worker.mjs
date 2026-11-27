const origin = 'https://publish-task.onrender.com';
const root = '/api/v1/work';
const tool = (name, description, properties, required, readOnlyHint = false, destructiveHint = false) => ({
  name, description, inputSchema: {type:'object', properties, required, additionalProperties:false},
  annotations: {readOnlyHint, destructiveHint, idempotentHint:readOnlyHint || name === 'publish_task'}
});
const str = {type:'string'};
const number = {type:'integer'};
const identity = {task_id:str, revision:number};
const consumer = {type:'string',pattern:'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'};
const fields = {title:str, brief:str, project:str, due_at:{type:['integer','null']},
  priority:{type:'string',enum:['low','normal','high']}};
const tools = [
  tool('publish_task','發布待討論工作，使用穩定的來源 ID 避免重複',{source_id:str,...fields},['source_id','title']),
  tool('list_tasks','查詢已發布的工作',{},[],true),
  tool('get_task','查詢一項工作和目前修訂版',{task_id:str},['task_id'],true),
  tool('update_task','以目前修訂版修改工作內容',{...identity,...fields},['task_id','revision']),
  tool('cancel_task','取消尚未回傳的工作及其待發來電',identity,['task_id','revision'],false,true),
  tool('read_results','依上次處理完畢的游標讀取已回傳決策及指示',{after:number},[],true),
  tool('resume_work','讀取這個工作流程尚未確認處理的 VERA 決策與指示',{consumer},['consumer'],true),
  tool('ack_results','僅在原工作系統已保存結果後，確認已依序處理的游標',
    {consumer,after:number,cursors:{type:'array',items:number,minItems:1,maxItems:50}},['consumer','after','cursors'])
];
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function route(name, args) {
  if (name === 'publish_task') return ['/tasks','POST',args];
  if (name === 'list_tasks') return ['/tasks','GET'];
  if (name === 'read_results') {
    const cursor = args.after ?? 0;
    if (!Number.isSafeInteger(cursor) || cursor < 0) throw Error('結果游標無效');
    return ['/results?after=' + cursor,'GET'];
  }
  if (name === 'resume_work' || name === 'ack_results') {
    if (typeof args.consumer !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(args.consumer)) {
      throw Error('接續工作識別碼無效');
    }
    const path = '/inbox/' + args.consumer;
    return name === 'resume_work' ? [path,'GET'] : [path,'PUT',{after:args.after,cursors:args.cursors}];
  }
  const {task_id, ...body} = args;
  if (typeof task_id !== 'string' || !uuid.test(task_id)) throw Error('工作 ID 無效');
  const method = {get_task:'GET',update_task:'PATCH',cancel_task:'DELETE'}[name];
  if (!method) throw Error('找不到工具');
  return ['/tasks/' + task_id,method,method === 'GET' ? undefined : body];
}

function reply(value, status = 200) {
  return Response.json(value,{status,headers:{'Cache-Control':'no-store'}});
}

function toolReply(id, value, isError = false) {
  return reply({jsonrpc:'2.0',id,result:{
    content:[{type:'text',text:typeof value === 'string' ? value : JSON.stringify(value)}],
    ...(isError ? {isError:true} : {})
  }});
}

function rpcError(id, code, message) {
  return reply({jsonrpc:'2.0',id,error:{code,message}});
}

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    if (path === '/' && request.method === 'GET') {
      const caller = request.headers.get('oai-authenticated-user-id');
      return reply({service:'VERA Nexus 工作連線',site_user_id:caller || null,
        connected:Boolean(caller && caller === env.VERA_SITE_OWNER_ID && env.VERA_WORK_TOKEN)});
    }
    if (path !== '/mcp' || request.method !== 'POST') return reply({error:'Not found'},404);
    let rpc;
    try {
      const body = await request.text();
      if (body.length > 30000) return reply({error:'Request too large'},413);
      rpc = JSON.parse(body);
    } catch { return rpcError(null,-32700,'Invalid JSON'); }
    const id = rpc?.id ?? null;
    if (rpc?.jsonrpc !== '2.0' || typeof rpc.method !== 'string') return rpcError(id,-32600,'Invalid request');
    if (rpc.method === 'server/discover') {
      return reply({jsonrpc:'2.0',id,result:{supportedVersions:['2026-07-28'],capabilities:{tools:{}}}});
    }
    if (rpc.method === 'tools/list') return reply({jsonrpc:'2.0',id,result:{tools}});
    if (rpc.method.startsWith('notifications/') && id === null) return new Response(null,{status:204});
    if (rpc.method !== 'tools/call') return rpcError(id,-32601,'Method not found');
    const caller = request.headers.get('oai-authenticated-user-id');
    if (!env.VERA_SITE_OWNER_ID || caller !== env.VERA_SITE_OWNER_ID) {
      return toolReply(id,'需要這個私人 Site 的擁有人身分。',true);
    }
    if (!env.VERA_WORK_TOKEN) return toolReply(id,'Render 工作來源的授權尚未設定。',true);
    const params = rpc.params || {};
    if (!tools.some(tool => tool.name === params.name)) return toolReply(id,'找不到工具。',true);
    const args = params.arguments ?? {};
    if (!args || typeof args !== 'object' || Array.isArray(args)) return toolReply(id,'工具參數無效。',true);
    try {
      const [target, method, body] = route(params.name, args);
      const response = await fetch(origin + root + target,{
        method,headers:{Authorization:'Bearer '+env.VERA_WORK_TOKEN,'Content-Type':'application/json'},
        body:body === undefined ? undefined : JSON.stringify(body),redirect:'error',
        signal:AbortSignal.timeout(12000)
      });
      if (!response.ok) return toolReply(id,'VERA 工作 API 回傳 HTTP '+response.status,true);
      return toolReply(id,await response.json());
    } catch (error) {
      if (['工作 ID 無效','結果游標無效','接續工作識別碼無效'].includes(error.message)) return toolReply(id,error.message,true);
      return toolReply(id,'目前無法連到 VERA 工作 API。',true);
    }
  }
};

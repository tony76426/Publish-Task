const FORMAT = 'vera-local-encrypted-2';
const ITERATIONS = 310000;
export const MAX_FILE = 3000000;
const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', {fatal:true});
const idPattern = /^[A-Za-z0-9-]{1,80}$/;
const uuid = () => crypto.randomUUID();
const safeText = (value, max) => typeof value === 'string' ? value.slice(0,max) : '';
const number = (value, max) => typeof value === 'number' && Number.isFinite(value) ? Math.min(max,Math.max(0,value)) : 0;
const object = value => value && typeof value === 'object' && !Array.isArray(value);

function uniqueId(value, seen) {
  const id = typeof value === 'string' && idPattern.test(value) && !seen.has(value) ? value : uuid();
  seen.add(id);
  return id;
}

export function normalise(value) {
  if (!object(value) || value.format !== 'vera-backup-1' || !Array.isArray(value.tasks) ||
      !Array.isArray(value.histories) || value.tasks.length>200 || value.histories.length>50 ||
      value.tasks.some(task=>!object(task)||typeof task.title!=='string') ||
      value.histories.some(call=>!object(call)||!Array.isArray(call.rows))) {
    throw Error('備份格式不支援，現有資料未變更。');
  }
  const taskIds = new Set(), historyIds = new Set();
  const profile = object(value.assistantProfile) ? value.assistantProfile : {};
  const usage = object(value.usage) ? value.usage : {};
  return {
    format:'vera-backup-1',
    tasks:value.tasks.map(task=>({
      id:uniqueId(task.id,taskIds),title:safeText(task.title,500),
      priority:['high','low','normal'].includes(task.priority)?task.priority:'normal',
      due:typeof task.due==='string'&&Number.isFinite(Date.parse(task.due))?safeText(task.due,48):'',
      done:task.done===true,notified:task.notified===true
    })),
    histories:value.histories.map(call=>({
      id:uniqueId(call.id,historyIds),at:safeText(call.at,120),topic:safeText(call.topic,300),
      source:['manual','local','cloud'].includes(call.source)?call.source:'manual',
      call_id:typeof call.call_id==='string'&&idPattern.test(call.call_id)?call.call_id:null,
      rows:call.rows.slice(0,800).filter(row=>object(row)&&typeof row.text==='string').map(row=>({
        role:row.role==='VERA'?'VERA':'你',text:safeText(row.text,12000)
      })),summary:safeText(call.summary,12000)
    })),
    notes:safeText(value.notes,16000),
    assistantProfile:{
      memory:safeText(profile.memory,4000),name:safeText(profile.name,300),
      style:['concise','warm','professional'].includes(profile.style)?profile.style:'concise',
      voice:['marin','cedar','coral','sage'].includes(profile.voice)?profile.voice:'',
      speed:[.9,1,1.15].includes(profile.speed)?profile.speed:1,useMemory:profile.useMemory===true,
      autoMemory:profile.autoMemory===true,autoReconnect:profile.autoReconnect===true
    },
    usage:Object.fromEntries(['seconds','input','output','estimatedUSD','pricedResponses','unpricedResponses']
      .map(key=>[key,number(usage[key],Number.MAX_SAFE_INTEGER)])),
    callLimit:Math.floor(number(value.callLimit,120))
  };
}

function base64(bytes) {
  let binary = '';
  for (let start = 0; start < bytes.length; start+=8192) {
    binary += String.fromCharCode(...bytes.subarray(start,start+8192));
  }
  return btoa(binary);
}

function bytes(value) {
  if (typeof value!=='string' || value.length>MAX_FILE) throw Error('備份內容無效。');
  return Uint8Array.from(atob(value),c=>c.charCodeAt(0));
}

async function derive(passphrase,salt) {
  if (typeof passphrase!=='string'||passphrase.length<12||passphrase.length>200) throw Error('備份密碼須介於 12 至 200 個字元。');
  const seed=await crypto.subtle.importKey('raw',encoder.encode(passphrase),'PBKDF2',false,['deriveKey']);
  return crypto.subtle.deriveKey({name:'PBKDF2',hash:'SHA-256',iterations:ITERATIONS,salt},
    seed,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);
}

export async function encryptBackup(value,passphrase) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plaintext=encoder.encode(JSON.stringify(normalise(value)));
  if (plaintext.length>2100000) throw Error('資料超過單檔備份上限，請先移除不需要的本機通話。');
  const key=await derive(passphrase,salt);
  const cipher=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:encoder.encode(FORMAT)},key,plaintext);
  return JSON.stringify({format:FORMAT,salt:base64(salt),iv:base64(iv),ciphertext:base64(new Uint8Array(cipher))});
}

export async function readBackup(raw,passphrase) {
  if (typeof raw!=='string'||raw.length>MAX_FILE) throw Error('備份檔過大或無效。');
  try {
    const value=JSON.parse(raw);
    if (value?.format!==FORMAT) return normalise(value);
    const salt=bytes(value.salt),iv=bytes(value.iv),cipher=bytes(value.ciphertext);
    if (salt.length!==16||iv.length!==12||cipher.length<16) throw Error('Invalid archive');
    const key=await derive(passphrase,salt);
    const payload=await crypto.subtle.decrypt({name:'AES-GCM',iv,additionalData:encoder.encode(FORMAT)},key,cipher);
    return normalise(JSON.parse(decoder.decode(payload)));
  } catch { throw Error('無法還原。請檢查備份檔與密碼，現有資料未變更。'); }
}

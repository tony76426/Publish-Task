'use strict';

(() => {
  const workRoute = '/api/v1/secretary';
  const stateNames = {open: '待聯繫', acknowledged: '已排定', answered: '已回傳', cancelled: '已取消',
    pending: '摘要排隊中', running: '正在整理', ready: '摘要已完成', failed: '摘要產生失敗'};
  const button = (label, action) => {
    const element = document.createElement('button');
    element.type = 'button';
    element.className = 'secondary';
    element.textContent = label;
    element.onclick = action;
    return element;
  };
  const message = (target, value) => { target.textContent = value; };
  const device = () => {
    try { return JSON.parse(window.VeraAndroid?.cloudDevice?.() || '{}'); } catch { return {}; }
  };
  async function requestWork(path, method = 'GET', data) {
    if (!token()) throw Error('請先登入 VERA');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(workRoute + path, {
        method, headers: {'Authorization': 'Bearer ' + token(), 'Content-Type': 'application/json'},
        body: data === undefined ? undefined : JSON.stringify(data),
        cache: 'no-store', signal: controller.signal
      });
      if (response.status === 204) return {};
      const value = await response.json();
      if (!response.ok) {
        const error = Error(value.error || ('HTTP ' + response.status));
        error.status = response.status;
        throw error;
      }
      return value;
    } finally { clearTimeout(timeout); }
  }
  function mount(section, content) {
    const card = document.createElement('section');
    card.className = 'card secretary-panel';
    card.innerHTML = content;
    $(section).prepend(card);
    return card;
  }
  const taskCard = mount('tasks', `
    <h2>雲端工作</h2><div class="secretary-actions"><label>專案 <select id="v3ProjectFilter"><option value="">全部專案</option></select></label>
    <button class="secondary" id="v3WorkRefresh" type="button">重新整理</button></div>
    <p id="v3WorkStatus" class="muted" role="status"></p><div id="v3WorkList"></div>
    <form id="v3Schedule" hidden>
      <p><strong id="v3ScheduleTask"></strong></p>
      <label>聯繫時間<input id="v3WorkWhen" type="datetime-local" required></label>
      <label class="secretary-check"><input id="v3WorkReturn" type="checkbox"> 摘要完成後，自動回傳我明確給出的決策及指示</label>
      <label class="secretary-check"><input id="v3WorkRetry" type="checkbox"> 未接時五分鐘後重撥一次</label>
      <div class="secretary-actions"><button type="submit">安排來電</button><button type="button" class="secondary" id="v3ScheduleClose">關閉</button></div>
    </form>`);
  const autoCard = mount('settings', `
    <h2>ChatGPT 自動聯繫</h2>
    <p>台灣時間每日 10:00–24:00；每日最多兩次，午夜前保留一分鐘安全緩衝。不影響手動安排。</p>
    <label class="secretary-check"><input id="v3AutoEnable" type="checkbox"> 允許 ChatGPT 安排本機來電</label>
    <label class="secretary-check"><input id="v3AutoReturn" type="checkbox"> 自動回傳我明確給出的決策及指示</label>
    <div class="secretary-actions"><button id="v3AutoSave" type="button">儲存授權</button><button id="v3AutoRefresh" type="button" class="secondary">查詢狀態</button></div>
    <p id="v3AutoStatus" role="status" class="muted">尚未查詢授權</p>`);
  async function refreshAuto() {
    try {
      const result = await requestWork('/auto-call');
      $('v3AutoEnable').checked = result.enabled && result.device_id === device().device_id;
      $('v3AutoReturn').checked = result.return_result;
      message($('v3AutoStatus'), result.enabled ? ($('v3AutoEnable').checked ? '本機已授權' : '另一裝置已授權') : '未開啟自動聯繫');
    } catch(error) { message($('v3AutoStatus'), error.message); }
  }
  $('v3AutoRefresh').onclick = refreshAuto;
  $('v3AutoSave').onclick = async () => {
    const enabled = $('v3AutoEnable').checked, installation = device();
    if(enabled && (!installation.device_id || !installation.enabled)) return message($('v3AutoStatus'), '請先註冊本機推播');
    if(enabled && !window.confirm('允許 ChatGPT 安排本機來電？可隨時取消授權。')) return;
    $('v3AutoSave').disabled = true;
    try {
      await requestWork('/auto-call','PUT',{enabled,device_id:installation.device_id || '',return_result:enabled && $('v3AutoReturn').checked});
      await refreshAuto();
    } catch(error) { message($('v3AutoStatus'),error.message); }
    finally { $('v3AutoSave').disabled = false; }
  };
  const archiveCard = mount('history', `
    <h2>雲端通話與決策</h2><p id="v3CallStatus" class="muted" role="status"></p>
    <div class="secretary-actions"><button type="button" class="secondary" id="v3CallRefresh">重新整理</button></div><div id="v3CallList"></div>`);
  const memoryCard = mount('settings', `
    <h2>雲端記憶</h2><div class="secretary-actions"><button type="button" id="v3MemoryAdd">新增記憶</button>
      <button type="button" class="secondary" id="v3MemoryRefresh">重新整理</button></div>
    <label>搜尋專案或內容<input type="search" id="v3MemoryQuery"></label>
    <p id="v3MemoryStatus" class="muted" role="status"></p><div id="v3MemoryList"></div>
    <form id="v3MemoryForm" hidden>
      <label>分類<select id="v3MemoryKind"><option value="note">記憶</option><option value="decision">重要決策</option></select></label>
      <label>專案<input id="v3MemoryProject" maxlength="80"></label>
      <label>標題<input id="v3MemoryTitle" maxlength="160" required></label>
      <label>內容<textarea id="v3MemoryNote" rows="4" maxlength="4000" required></textarea></label>
      <div class="secretary-actions"><button type="submit">儲存記憶</button><button type="button" class="secondary" id="v3MemoryClose">關閉</button></div>
    </form>
    <div class="secretary-actions"><button type="button" class="secondary" id="v3Export">備份雲端記憶</button>
      <button type="button" class="secondary" id="v3Import">合併記憶備份</button><input id="v3MemoryFile" type="file" accept="application/json" hidden></div>`);
  $('settings').append(memoryCard);
  const loginCard = $('token').closest('.card');
  if (loginCard) $('settings').prepend(loginCard);
  const diagnostics = document.createElement('p');
  diagnostics.className = 'muted';
  diagnostics.setAttribute('role','status');
  $('cloudStorage').closest('.card').append(diagnostics);
  const banner = document.createElement('p');
  banner.className = 'secretary-status muted';
  banner.setAttribute('role', 'status');
  $('status').after(banner);
  $('summary').hidden = true;
  $('callLimit').value = String(read('callLimit', 20));
  for (const card of [taskCard, archiveCard, memoryCard]) card.setAttribute('aria-label', card.querySelector('h2').textContent);
  const heading = document.querySelector('header h1');
  if (heading) heading.textContent = 'VERA Nexus';
  document.querySelector('button[data-page="history"]').textContent = '通話紀錄';
  const deskHead = $('tasks').querySelector('.desk-head');
  if (deskHead) $('tasks').prepend(deskHead);
  const localHistoryHeading = $('historySearch').closest('.card').querySelector('h2');
  if (localHistoryHeading) localHistoryHeading.textContent = '本機通話紀錄';
  for (const card of [...$('settings').children]) {
    if (!card.matches('.card') || card===loginCard || card===memoryCard) continue;
    const heading = card.querySelector(':scope > h2');
    if (!heading) continue;
    const section = document.createElement('details');
    const summary = document.createElement('summary');
    section.className='settings-group';
    summary.textContent=heading.textContent;
    card.before(section);
    section.append(summary,card);
    heading.hidden=true;
  }

  let work = [], scheduling = null, memory = [], editing = null;
  let flushing = false, callsRequest = 0, retryAfter = 0, lastError = '';
  let outbox = read('workOutbox', []);
  if (!Array.isArray(outbox)) outbox = [];
  const time = stamp => new Date(stamp * 1000).toLocaleString('zh-TW');
  const row = (title, detail) => {
    const card = document.createElement('article');
    card.className = 'secretary-item';
    const strong = document.createElement('strong');
    strong.textContent = title;
    const p = document.createElement('p');
    p.textContent = detail;
    card.append(strong, p);
    return card;
  };
  function showWork() {
    const filter = $('v3ProjectFilter').value;
    $('v3WorkList').replaceChildren();
    const visible = work.filter(item => !filter || item.project === filter);
    for (const item of visible) {
      const labels = [item.project, {high:'高優先',normal:'一般',low:'低優先'}[item.priority],
        stateNames[item.state], item.due_at ? time(item.due_at) : ''].filter(Boolean);
      const card = row(item.title, labels.join(' · '));
      if (item.brief) {
        const briefing = document.createElement('p');
        briefing.textContent = item.brief;
        card.append(briefing);
      }
      if (item.state === 'open' || item.state === 'acknowledged') {
        card.append(button('安排工作來電', () => {
          scheduling = item;
          $('v3ScheduleTask').textContent = item.title;
          $('v3Schedule').hidden = false;
          $('v3WorkWhen').focus();
        }));
      }
      $('v3WorkList').append(card);
    }
    if (!visible.length) $('v3WorkList').append(row('目前沒有雲端工作', '授權的工作來源發布後會顯示在這裡。'));
  }
  async function refreshWork() {
    try {
      const result = await requestWork('/tasks');
      work = result.tasks;
      const select = $('v3ProjectFilter');
      const previous = select.value;
      select.replaceChildren(new Option('全部專案', ''));
      for (const name of [...new Set(work.map(item => item.project).filter(Boolean))].sort()) select.add(new Option(name, name));
      if (Array.from(select.options).some(option => option.value === previous)) select.value = previous;
      message($('v3WorkStatus'), '');
      showWork();
    } catch (error) { message($('v3WorkStatus'), error.message); }
  }
  $('v3WorkRefresh').onclick = refreshWork;
  $('v3ProjectFilter').onchange = showWork;
  $('v3ScheduleClose').onclick = () => { $('v3Schedule').hidden = true; scheduling = null; };
  $('v3Schedule').onsubmit = async event => {
    event.preventDefault();
    const item = scheduling;
    if (!item) return;
    const due = Math.floor(new Date($('v3WorkWhen').value).getTime() / 1000);
    if (!Number.isFinite(due) || due <= Date.now() / 1000) return message($('v3WorkStatus'), '請選未來的聯繫時間');
    const installation = device();
    if (!installation.device_id || !installation.enabled) return message($('v3WorkStatus'), '請先到「雲端」註冊本機推播');
    const returnResult = $('v3WorkReturn').checked;
    const retry = $('v3WorkRetry').checked;
    const signature = [due, returnResult, retry].join(':');
    if (item.scheduleKey !== signature) {
      item.scheduleKey = signature;
      item.eventId = crypto.randomUUID();
    }
    const submit = event.submitter;
    if (submit) submit.disabled = true;
    try {
      await requestWork('/tasks/' + item.id + '/call', 'POST', {
        due_at: due, device_id: installation.device_id, event_id: item.eventId,
        return_result: returnResult, retry
      });
      $('v3Schedule').reset();$('v3Schedule').hidden = true;scheduling = null;
      await refreshWork();
      message($('v3WorkStatus'), '工作來電已排定');
    } catch (error) { message($('v3WorkStatus'), error.message); }
    finally { if (submit) submit.disabled = false; }
  };

  function trimTranscript(snapshot) {
    let remaining = 48000;
    const candidates = snapshot.rows.slice(0, 800);
    const lines = [];
    let partial = Boolean(snapshot.transcript_partial || candidates.length !== snapshot.rows.length);
    for (const entry of candidates) {
      if (!remaining) { partial = true; break; }
      const line = entry.text.slice(0, Math.min(12000, remaining));
      remaining -= line.length;
      if (line.length !== entry.text.length) partial = true;
      lines.push({role: entry.role, text: line});
    }
    return {id: snapshot.id, event_id: snapshot.event_id, device_id: snapshot.device_id,
      topic: snapshot.topic, end_reason: snapshot.end_reason, transcript_partial: partial, rows: lines};
  }
  function updateBanner(value = '') {
    banner.textContent = value || (outbox.length ? '待同步通話 ' + outbox.length + ' 筆' : '');
  }
  async function flush() {
    if (flushing || !token() || !navigator.onLine || Date.now() < retryAfter || !outbox.length) return;
    flushing = true;
    try {
      let deferred = '';
      for (const item of [...outbox]) {
        try {
          await requestWork('/calls', 'POST', item);
        } catch (error) {
          if (![400,409,413].includes(error.status)) throw error;
          deferred = error.message;
          continue;
        }
        const next = outbox.filter(call => call.id !== item.id);
        if (!write('workOutbox', next, true)) throw Error('本機同步狀態無法更新');
        outbox = next;
        lastError = '';
        updateBanner(outbox.length ? '' : '通話已保存，將自動整理摘要');
      }
      if (deferred) throw Error(deferred);
      if (!$('history').hidden) await refreshCalls();
    } catch (error) {
      lastError = error.message;
      retryAfter = Date.now() + (error.status === 409 ? 5000 : 15000);
      updateBanner('摘要等待同步：' + lastError);
    } finally { flushing = false; }
  }
  function queue(snapshot) {
    if (!snapshot) return;
    const item = trimTranscript(snapshot);
    if (outbox.some(pending => pending.id === item.id)) return;
    const next = [...outbox, item];
    if (next.length <= 30 && write('workOutbox', next, true)) {
      outbox = next;
      write('activeCall', null, true);
      updateBanner();
      void flush();
    } else updateBanner('本機暫存已滿，請先連線同步既有通話。');
  }
  window.veraQueueFinished = queue;
  window.veraCheckpoint = snapshot => { if (snapshot?.rows?.length) write('activeCall', trimTranscript(snapshot), true); };
  window.veraLocalClear = () => { outbox = []; lastError = '';retryAfter=0;updateBanner(); };
  const unfinished = read('activeCall', null);
  if (unfinished) queue({...unfinished, transcript_partial:true});
  window.addEventListener('online', () => { retryAfter = 0; void flush(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void flush(); });
  setInterval(() => {
    if (document.hidden) return;
    void flush();
    if (!$('history').hidden) void refreshCalls();
  }, 8000);

  async function refreshCalls() {
    const generation = ++callsRequest;
    try {
      const response = await requestWork('/calls');
      if (generation !== callsRequest) return;
      $('v3CallList').replaceChildren();
      for (const item of response.calls) {
        const card = row(item.topic || 'VERA 通話',
          time(item.created_at) + ' · ' + (stateNames[item.state] || item.state) + (item.transcript_partial ? ' · 逐字稿可能不完整' : ''));
        if (item.error) card.append(row('診斷', item.error));
        if (item.result) {
          for (const [title, content] of [
            ['摘要', item.result.summary], ['決策', item.result.decisions.join('\n')],
            ['工作指示', item.result.instructions.join('\n')]
          ]) if (content) card.append(row(title, content));
          const decisions = item.result.decisions.join('\n').slice(0, 4000);
          if (decisions) card.append(button('保存為重要決策', () => {
            page('settings');openMemory({kind:'decision', title:item.topic || '通話決策', note:decisions});
          }));
        }
        if (item.rows.length) {
          const details = document.createElement('details');
          const title = document.createElement('summary');
          title.textContent = '查看逐字稿';
          details.append(title, row('', item.rows.map(entry => entry.role + '：' + entry.text).join('\n')));
          card.append(details);
        }
        card.append(button('刪除雲端通話', async () => {
          if (!confirm('刪除雲端逐字稿、摘要及此通話的待領取結果？已由外部取得的副本仍由該系統保存。')) return;
          try { await requestWork('/calls/' + item.id, 'DELETE');await refreshCalls(); }
          catch (error) { message($('v3CallStatus'), error.message); }
        }));
        $('v3CallList').append(card);
      }
      message($('v3CallStatus'), outbox.length ? '本機尚有 ' + outbox.length + ' 筆等待同步。' :
        response.calls.length ? '' : '完成通話後會自動整理並出現在這裡。');
    } catch (error) {
      if (generation === callsRequest) message($('v3CallStatus'), error.message);
    }
  }
  $('v3CallRefresh').onclick = refreshCalls;

  function openMemory(item = {}) {
    editing = item.id ? item : null;
    $('v3MemoryKind').value = item.kind || 'note';
    $('v3MemoryProject').value = item.project || '';
    $('v3MemoryTitle').value = item.title || '';
    $('v3MemoryNote').value = item.note || '';
    $('v3MemoryForm').hidden = false;
    $('v3MemoryTitle').focus();
  }
  function showMemory() {
    const q = $('v3MemoryQuery').value.trim().toLocaleLowerCase();
    const list = $('v3MemoryList');
    list.replaceChildren();
    for (const item of memory) {
      if (q && ![item.project, item.title, item.note].join(' ').toLocaleLowerCase().includes(q)) continue;
      const card = row(item.title, [item.project, item.kind === 'decision' ? '重要決策' : '記憶'].filter(Boolean).join(' · '));
      const note = document.createElement('p');note.textContent=item.note;card.append(note);
      card.append(button('編輯', () => openMemory(item)), button('刪除', async () => {
        if (!confirm('刪除這筆雲端記憶？')) return;
        try { await requestWork('/memory/' + item.id, 'DELETE', {revision: item.revision});await refreshMemory(); }
        catch (error) { message($('v3MemoryStatus'), error.message); }
      }));
      list.append(card);
    }
  }
  async function refreshMemory() {
    try {
      memory = (await requestWork('/memory')).entries;
      showMemory();message($('v3MemoryStatus'), memory.length ? '' : '目前沒有雲端記憶。');
    } catch (error) { message($('v3MemoryStatus'), error.message); }
  }
  $('v3MemoryQuery').oninput = showMemory;
  $('v3MemoryAdd').onclick = () => openMemory();
  $('v3MemoryClose').onclick = () => { $('v3MemoryForm').hidden = true;editing = null; };
  $('v3MemoryRefresh').onclick = refreshMemory;
  $('v3MemoryForm').onsubmit = async event => {
    event.preventDefault();
    const item = {kind:$('v3MemoryKind').value, project:$('v3MemoryProject').value,
      title:$('v3MemoryTitle').value, note:$('v3MemoryNote').value};
    const submit = event.submitter;
    if (submit) submit.disabled = true;
    try {
      if (editing) await requestWork('/memory/' + editing.id, 'PUT', {...item,revision:editing.revision});
      else {
        const fingerprint = JSON.stringify(item);
        if (event.target.dataset.pendingBody !== fingerprint) {
          event.target.dataset.pendingBody=fingerprint;
          event.target.dataset.pendingId=crypto.randomUUID();
        }
        await requestWork('/memory', 'POST', {...item,id:event.target.dataset.pendingId});
        delete event.target.dataset.pendingBody;delete event.target.dataset.pendingId;
      }
      $('v3MemoryForm').hidden = true;editing = null;await refreshMemory();
    } catch (error) { message($('v3MemoryStatus'), error.message); }
    finally { if (submit) submit.disabled = false; }
  };
  $('v3Export').onclick = async () => {
    try {
      const raw = JSON.stringify(await requestWork('/backup'));
      if (window.VeraAndroid?.exportBackup) window.VeraAndroid.exportBackup(raw);
      else {
        const url = URL.createObjectURL(new Blob([raw], {type:'application/json'}));
        const download = document.createElement('a');download.href=url;download.download='VERA-雲端記憶備份.json';download.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch (error) { message($('v3MemoryStatus'), error.message); }
  };
  async function importArchive(raw) {
    const data = JSON.parse(raw);
    if (data.format !== 'vera-memory-enc-v1') throw Error('這個檔案不是雲端記憶備份');
    if (!confirm('將備份中的記憶合併到現有資料？同 ID 的現有記憶會保留。')) return;
    const response = await requestWork('/backup', 'POST', {archive:data.archive});
    await refreshMemory();
    message($('v3MemoryStatus'), '已匯入 ' + response.imported + ' 筆記憶');
  }
  const backupDialog=document.createElement('dialog');
  backupDialog.className='desk-dialog';
  backupDialog.setAttribute('aria-labelledby','v3BackupTitle');
  backupDialog.innerHTML=`<form method="dialog">
    <h2 id="v3BackupTitle"></h2>
    <label>備份密碼<input id="v3BackupPassword" type="password" autocomplete="off" minlength="12" maxlength="200" required></label>
    <p class="muted" id="v3BackupHelp"></p>
    <div class="secretary-actions"><button type="submit" value="continue">繼續</button>
    <button type="button" id="v3BackupCancel" class="secondary">取消</button></div>
  </form>`;
  document.body.append(backupDialog);
  $('v3BackupCancel').onclick=()=>backupDialog.close('cancel');
  function backupPassword(mode) {
    if(backupDialog.open)return Promise.resolve(null);
    $('v3BackupTitle').textContent=mode==='export'?'設定加密備份密碼':'解鎖本機備份';
    $('v3BackupHelp').textContent=mode==='export'?'請使用至少 12 個字元。還原時需要同一密碼。':'輸入匯出備份時設定的密碼。';
    $('v3BackupPassword').value='';
    return new Promise(resolve=>{
      backupDialog.addEventListener('close',()=>{
        const passphrase=backupDialog.returnValue==='continue'?$('v3BackupPassword').value:null;
        $('v3BackupPassword').value='';
        resolve(passphrase);
      },{once:true});
      backupDialog.returnValue='cancel';
      backupDialog.showModal();
      $('v3BackupPassword').focus();
    });
  }
  function localSnapshot() {
    return {format:'vera-backup-1',tasks,histories,notes:read('notes',''),assistantProfile:read('assistantProfile',{}),
      usage:read('usage',{}),callLimit:read('callLimit',20)};
  }
  function applyLocalSnapshot(backup) {
    if (busy) throw Error('請先結束通話再還原。');
    const native=window.VeraAndroid;
    const values=['tasks','history','notes','assistantProfile','usage','callLimit'].map(key=>{
      const raw=JSON.stringify(backup[key==='history'?'histories':key]);
      const name=(native?.sealPrivateData?'vera.private.':'vera.')+key;
      const encoded=native?.sealPrivateData?native.sealPrivateData(key,raw):raw;
      if(!encoded)throw Error('資料無法安全保存，現有資料未變更。');
      return {name,encoded,previous:localStorage.getItem(name)};
    });
    const saved=[];
    try {
      for (const entry of values) {
        localStorage.setItem(entry.name,entry.encoded);
        saved.push(entry);
      }
    } catch (error) {
      for(const entry of saved.reverse()){
        if(entry.previous===null)localStorage.removeItem(entry.name);
        else localStorage.setItem(entry.name,entry.previous);
      }
      throw Error('本機空間不足，未套用備份。',{cause:error});
    }
    tasks=backup.tasks;histories=backup.histories;
    $('notes').value=backup.notes;$('callLimit').value=String(backup.callLimit);
    loadProfile();renderTasks();renderHistory();showUsage();
    lastTaskSync=null;syncNativeTasks();
  }
  function downloadLocal(raw) {
    if(window.VeraAndroid?.exportBackup){window.VeraAndroid.exportBackup(raw);return;}
    const url=URL.createObjectURL(new Blob([raw],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='VERA-本機加密備份.json';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  $('backup').textContent='匯出本機加密備份';
  $('backup').onclick=async()=>{
    try {
      const password=await backupPassword('export');
      if(password===null)return;
      const {encryptBackup}=await import('/assets/vera-backup.mjs');
      downloadLocal(await encryptBackup(localSnapshot(),password));
    } catch(error){alert(error.message);}
  };
  window.veraRestoreBackup=async raw=>{
    try {
      const format=JSON.parse(raw)?.format;
      if(format==='vera-memory-enc-v1'){await importArchive(raw);return;}
      const encrypted=format==='vera-local-encrypted-2';
      const password=encrypted?await backupPassword('restore'):'';
      if(password===null)return;
      const {readBackup}=await import('/assets/vera-backup.mjs');
      const data=await readBackup(raw,password);
      if(!confirm('用這份備份還原本機工作、通話與筆記？'))return;
      applyLocalSnapshot(data);
      alert('已還原本機資料。');
    } catch(error){alert(error.message);}
  };
  $('v3Import').onclick = () => {
    if (window.VeraAndroid?.importBackup) window.VeraAndroid.importBackup();
    else $('v3MemoryFile').click();
  };
  $('v3MemoryFile').onchange = async event => {
    const file = event.target.files[0];if (!file) return;
    try { if (file.size>240000) throw Error('檔案太大');await importArchive(await file.text()); }
    catch(error){message($('v3MemoryStatus'),error.message);}
    finally {event.target.value='';}
  };
  let lastPage=document.querySelector('.nav .sel')?.dataset.page;
  window.veraPageChanged = selected => {
    if(selected!==lastPage){window.scrollTo(0,0);lastPage=selected;}
    if (selected === 'tasks') void refreshWork();
    if (selected === 'history') void refreshCalls();
    if (selected === 'settings' && token()) void refreshMemory();
    if (selected === 'cloud' && token()) {
      requestWork('/diagnostics').then(data => {
        diagnostics.textContent = '雲端摘要 ' + data.calls_last_day + '／' + data.daily_limit
          + '（近 24 小時）・等待處理 ' + data.pending_summaries + ' 筆・可用空間 ' + data.disk_free_mb + ' MB';
      }).catch(error => { diagnostics.textContent = error.message; });
    }
    if (!lastError) void flush();
  };
})();

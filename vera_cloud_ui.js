(() => {
  'use strict';

  const states = {
    queued: '等待發送', sending: '發送中', fcm_accepted: 'Firebase 已受理',
    received: '手機已收到', ringing: '已顯示來電', accepted: '已接聽',
    declined: '已拒絕', missed: '未接', quiet: '勿擾時段', busy: '手機忙線中',
    blocked: '通知未授權', failed: '發送失敗', cancelled: '已取消',
    send_unknown: '發送未獲確認', unconfirmed: '尚無手機回執',
  };
  const fixes = {
    sender_not_configured: '請檢查 Render 的 Firebase 發送憑證。',
    device_unregistered: '請在此手機重新啟用 Firebase。',
    expired: '排程已逾有效時間，請重新安排。',
    firebase_send_error: '請檢查 Render 日誌及服務帳戶權限。',
    no_receipt: '請檢查手機網路、通知和背景執行權限。',
  };
  let loading = false;
  let latestApk = '';
  const local = () => {
    try { return JSON.parse(window.VeraAndroid?.cloudDevice?.() || '{}'); }
    catch { return {}; }
  };
  const date = value => new Date(value * 1000).toLocaleString('zh-TW');
  const label = (value, yes, no) => value === true ? yes : value === false ? no : '尚未確認';
  const timeout = ms => typeof AbortSignal !== 'undefined' && AbortSignal.timeout
    ? AbortSignal.timeout(ms) : undefined;

  async function cloudRequest(path, body, method = 'POST') {
    if (!token()) throw Error('請先在設定驗證私人連線。');
    const response = await fetch('/api/cloud/' + path, {
      method, cache: 'no-store',
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token()},
      body: JSON.stringify(body),
      signal: timeout(7000),
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'HTTP ' + response.status);
    return data;
  }

  function row(title, detail) {
    const box = document.createElement('div');
    box.className = 'entry cloud-entry';
    const heading = document.createElement('b');
    const note = document.createElement('p');
    heading.textContent = title;
    note.textContent = detail;
    box.append(heading, note);
    return box;
  }

  function renderEvents(events, device) {
    const list = $('cloudEvents');
    list.replaceChildren();
    if (!events.length) list.textContent = '此裝置尚無雲端來電紀錄。';
    for (const event of events) {
      const title = event.test ? 'Firebase 測試來電' : event.retry_of ? '雲端重撥' : '雲端主動來電';
      const status = states[event.state] || '未知狀態';
      const entry = row(title + '・' + status, date(event.due) + (fixes[event.reason] ? '・' + fixes[event.reason] : ''));
      if (event.trail?.length) {
        const timeline = document.createElement('small');
        timeline.textContent = event.trail.map(item => states[item.state] || item.state).join(' → ');
        entry.append(timeline);
      }
      if (event.state === 'queued') {
        const cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.className = 'secondary';
        cancel.textContent = '取消來電';
        cancel.onclick = async () => {
          cancel.disabled = true;
          try { await cloudRequest('calls', {device_id: device, event_id: event.event_id}, 'DELETE'); await refresh(); }
          catch (error) { text('cloudNotice', error.message); cancel.disabled = false; }
        };
        entry.append(cancel);
      }
      list.append(entry);
    }
  }

  function renderCalls() {
    const box = $('cloudLocalCalls');
    box.replaceChildren();
    const log = reminderState().log || [];
    for (const e of log.slice(0, 12)) {
      const type = e.kind?.startsWith('remote') ? '雲端來電' : '本機提醒';
      box.append(row(type + '・' + (e.state === 'opened' ? '已接聽' : states[e.state] || e.state),
        new Date(e.at).toLocaleString('zh-TW')));
    }
    if (!log.length) box.textContent = '尚無手機主動來電紀錄。';
  }

  async function refresh() {
    if (loading) return;
    loading = true;
    const info = local();
    const native = Boolean(window.VeraAndroid?.cloudDevice);
    text('cloudFirebase', native ? label(info.configured, 'APK 已載入 Firebase 設定', 'APK 缺少 Firebase 設定') : '需使用新版 Android APK');
    text('cloudApkVersion', ({7: '0.1.6', 8: '0.2.0', 9: '0.2.1', 10: '0.3.0', 11: '0.3.0'})[window.VeraAndroid?.apkVersion?.()] || '網頁或未知版本');
    text('cloudNotifications', native ? label(info.notifications, '通知已允許', '需要允許通知') : '僅 Android 支援');
    text('cloudFullscreen', native ? label(info.fullscreen && reminderState().fullscreen, '全螢幕來電已允許', '使用一般通知') : '僅 Android 支援');
    text('cloudDevice', info.enabled ? '確認中' : '此手機尚未啟用');
    text('cloudCredentials', token() ? '確認中' : '驗證私人連線後顯示');
    const canEnroll = Boolean(info.configured && info.notifications && token());
    $('cloudEnable').disabled = !canEnroll;
    $('cloudTest').disabled = !canEnroll;
    $('cloudDisable').disabled = !info.enabled;
    $('cloudAllow').disabled = !native;
    $('cloudSchedule').disabled = true;
    renderCalls();
    const taskSelect = $('cloudTask');
    const selectedTask = taskSelect.value;
    taskSelect.replaceChildren(new Option('不連結工作', ''));
    for (const task of tasks.filter(item => !item.done).slice(0, 60)) {
      taskSelect.add(new Option(task.title.slice(0, 55), task.id));
    }
    if (Array.from(taskSelect.options).some(option => option.value === selectedTask)) taskSelect.value = selectedTask;
    const backend = fetch('/health', {cache: 'no-store', signal: timeout(5000)})
      .then(async response => {
        if (!response.ok) throw Error('health');
        const health = await response.json();
        text('cloudRender', health.status === 'ok' ? '在線・' + health.version : '狀態異常');
      }).catch(() => text('cloudRender', '無法取得回應'));
    try {
      if (!token()) {
        renderEvents([], '');
        return;
      }
      const result = await cloudRequest('status', {device_id: info.device_id || ''});
      text('cloudDevice', info.enabled ? label(result.registered, '此手機已註冊', '尚未同步，請重新註冊') : '此手機尚未啟用');
      text('cloudCredentials', label(result.credentials_configured, 'Render 找到憑證檔', 'Render 缺少憑證檔'));
      text('cloudStorage', result.storage_configured ? '已指定資料庫路徑' : '服務重部署可能清空雲端排程');
      $('cloudSchedule').disabled = !(canEnroll && info.enabled && result.registered && result.credentials_configured);
      renderEvents(result.events || [], info.device_id);
    } catch (error) {
      text('cloudDevice', '未能查詢');
      text('cloudCredentials', '尚未確認');
      text('cloudNotice', error.message);
      renderEvents([], '');
    } finally {
      await backend;
      loading = false;
    }
  }

  $('cloudEnable').onclick = () => {
    text('cloudNotice', '正在註冊，請稍候再重新整理。');
    window.VeraAndroid?.enableCloudPush?.();
    setTimeout(refresh, 1400);
  };
  $('cloudTest').onclick = () => {
    text('cloudNotice', '正在準備測試。以手機收到來電和回執為準。');
    window.VeraAndroid?.testPush?.();
    setTimeout(refresh, 1400);
  };
  $('cloudDisable').onclick = () => { window.VeraAndroid?.disablePush?.(); setTimeout(refresh, 700); };
  $('cloudAllow').onclick = () => $('notificationPermission').click();
  $('cloudRefresh').onclick = refresh;

  $('cloudForm').onsubmit = async event => {
    event.preventDefault();
    const due = Math.floor(new Date($('cloudDue').value).getTime() / 1000);
    if (!Number.isFinite(due) || due <= Date.now() / 1000) {
      text('cloudNotice', '請選擇未來的來電時間。');
      return;
    }
    $('cloudSchedule').disabled = true;
    try {
      await cloudRequest('calls', {
        device_id: local().device_id, event_id: crypto.randomUUID(), due,
        purpose: $('cloudPurpose').value.trim(), task_id: $('cloudTask').value, retry: $('cloudRetry').checked,
      });
      $('cloudForm').reset();
      text('cloudNotice', '雲端來電已排程。手機接聽前會遵守勿擾設定。');
      await refresh();
    } catch (error) {
      text('cloudNotice', error.message);
      $('cloudSchedule').disabled = false;
    }
  };

  async function checkApk() {
    try {
      const endpoint = secretaryMode?'/api/v1/secretary/update':'/api/apk/latest';
      const response = await fetch(endpoint, {cache: 'no-store', signal: timeout(7000)});
      const build = await response.json();
      if(secretaryMode&&response.ok&&(!build.available||build.version_code<=Number(window.VeraAndroid?.apkVersion?.()||0))){
        text('cloudApkInfo',build.available?'已使用目前發布的版本':'目前沒有已驗證簽章可供升級的版本');
        return;
      }
      const validTag=secretaryMode?/^vera-nexus-v\d+\.\d+\.\d+-fcm-\d+-r\d+$/:/^vera-nexus-v0\.2\.1-fcm-\d+-r\d+$/;
      const exactUrl='https://github.com/tony76426/Publish-Task/releases/download/'+build.tag+'/VERA-Nexus.apk';
      if (!response.ok || !validTag.test(build.tag) || build.url!==exactUrl) {
        throw Error('暫時無法取得新版 APK');
      }
      latestApk = build.url;
      $('cloudDownload').disabled = false;
      text('cloudApkInfo', '最新版 ' + build.version + (build.android_firebase ? '・內含 Firebase 客戶端設定' : '・僅本機提醒測試'));
    } catch (error) {
      text('cloudApkInfo', error.message);
    }
  }
  $('cloudDownload').onclick = () => {
    if (!latestApk) return;
    if (window.VeraAndroid?.openVeraUpdate) window.VeraAndroid.openVeraUpdate(latestApk);
    else window.location.assign(latestApk);
  };

  window.veraRefreshCloud = () => { refresh(); if (!latestApk) checkApk(); };
  setInterval(() => { if (!document.hidden && !$('cloud').hidden) refresh(); }, 8000);
  window.veraOpenCloudCall = async (eventId, kind) => {
    if (kind === 'remote-test') {
      page('cloud');
      text('cloudNotice', '已在這支手機接聽 Firebase 測試來電，未啟用麥克風。');
      return;
    }
    if (!token()) { page('settings'); return; }
    const current = epoch;
    let topic = 'VERA 遠端主動聯繫';
    let context = '', retrieved = false;
    const deviceId = local().device_id;
    // The local receipt is queued before the WebView opens. Briefly allow it to arrive.
    const attempts=secretaryMode?5:3;
    for (let attempt = 0; attempt < attempts; attempt++) {
      try {
        const data = await cloudRequest('context', {device_id: deviceId, event_id: eventId});
        const task = tasks.find(item => item.id === data.task_id);
        topic = data.purpose || task?.title || topic;
        context = data.work_context || '';
        retrieved = true;
        break;
      } catch {
        if (attempt + 1 < attempts) await new Promise(resolve => setTimeout(resolve, 450+attempt*180));
      }
      if (current !== epoch || document.hidden || busy) return;
    }
    if (current !== epoch || document.hidden || busy) return;
    if(secretaryMode&&!retrieved){
      page('cloud');
      text('cloudNotice','無法取得這通來電的聯繫目的，請確認網路與來電狀態後再安排。');
      return;
    }
    $('topic').value = topic.slice(0, 300);
    page('home');
    start(false, 'cloud', {device_id:deviceId,event_id:eventId,work_context:context});
  };
})();

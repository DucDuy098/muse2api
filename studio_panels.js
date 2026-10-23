/* Chat sessions and Telegram settings for the existing authenticated admin. */
function setupMusePanels(api, getKey) {
  const el = id => document.getElementById(id);
  let sessions;
  try { sessions = JSON.parse(localStorage.getItem('muse2api_chat_sessions') || '[]'); }
  catch { sessions = []; }
  if (!Array.isArray(sessions)) sessions = [];
  let current = sessions[0], busy = false;
  const save = () => {
    try { localStorage.setItem('muse2api_chat_sessions', JSON.stringify(sessions.slice(0, 30))); }
    catch { el('chatStatus').textContent = 'Không lưu được lịch sử trên trình duyệt. Nội dung vẫn đang ở trang này.'; }
  };
  const node = (tag, text, parent) => { const n = document.createElement(tag); n.textContent = text; parent.append(n); return n; };
  function render() {
    el('chatSessions').replaceChildren();
    for (const session of sessions) {
      const option = node('option', session.title, el('chatSessions')); option.value = session.id;
    }
    if (current){el('chatSessions').value = current.id;if(el('chatAccount'))el('chatAccount').value=current.account_id||'';}
    el('chatMessages').replaceChildren();
    for (const message of current?.messages || []) {
      const box = node('div', '', el('chatMessages')); box.className = 'chat-message ' + message.role;
      node('b', message.role === 'user' ? 'Bạn' : 'Muse', box);
      node('div', message.content || '', box).style.whiteSpace = 'pre-wrap';
      for (const item of message.media || []) {
        const media = document.createElement(item.kind === 'video' ? 'video' : 'img');
        media.src = item.url; media.style.maxWidth = '100%'; media.style.maxHeight = '420px';
        if (item.kind === 'video') { media.controls = true; media.preload = 'metadata'; }
        box.append(media);
        const link = node('a', 'Tải ' + item.filename, box); link.href = item.url; link.download = item.filename;
      }
    }
    el('chatMessages').scrollTop = el('chatMessages').scrollHeight;
  }
  function fresh() {
    if (busy) return;
    current = {account_id:el('chatAccount')?.value||null,id: crypto.randomUUID(), title: 'Chat mới', messages: []}; sessions.unshift(current); save(); render();
  }
  if (!current) fresh(); else render();
  document.addEventListener('muse-accounts-ready',()=>{if(current?.account_id&&el('chatAccount'))el('chatAccount').value=current.account_id});
  el('chatNew').onclick = fresh;
  if(el('chatAccount'))el('chatAccount').onchange=()=>{if(!busy)fresh()};
  el('chatSessions').onchange = () => { if (!busy) { current = sessions.find(x => x.id === el('chatSessions').value); render(); } };
  el('chatSend').onclick = async () => {
    const text = el('chatInput').value.trim();
    if (busy || !text) return;
    if (text.length > 30000) { el('chatStatus').textContent = 'Tin nhắn tối đa 30.000 ký tự'; return; }
    busy = true;if(el('chatAccount'))el('chatAccount').disabled=true; el('chatSend').disabled = el('chatNew').disabled = el('chatSessions').disabled = true;
    const before = current.messages.length;
    current.messages.push({role: 'user', content: text});
    if (before === 0) current.title = text.slice(0, 55);
    el('chatInput').value = '';
    render(); el('chatStatus').textContent = 'Muse đang trả lời…';
    try {
      const response = await api('/v1/studio/chat', {method:'POST', body:JSON.stringify({account_id:current.account_id||el('chatAccount')?.value||null, session_id:current.id, prompt:text, resume_only:before>0})});
      current.account_id=response.account_id||current.account_id;const answer = response.message;
      if (response.warnings?.length) answer.content = (answer.content || '') + '\n\n' + response.warnings.join('\n');
      current.messages.push(answer); save(); render(); el('chatStatus').textContent = '';
    } catch (e) {
      current.messages.splice(before);
      if (!el('chatInput').value.trim()) el('chatInput').value = text;
      render(); el('chatStatus').textContent = e.message;
    } finally { busy = false;if(el('chatAccount'))el('chatAccount').disabled=false; el('chatSend').disabled = el('chatNew').disabled = el('chatSessions').disabled = false; }
  };
  el('chatInput').onkeydown = event => { if (event.ctrlKey && event.key === 'Enter') { event.preventDefault(); el('chatSend').click(); } };
  async function loadTelegram() {
    try {
      const data = await api('/v1/telegram/settings');
      el('telegramEnabled').checked = data.enabled; el('telegramOriginal').checked = data.send_original;
      el('telegramUserIds').value = data.user_ids.join(', '); el('telegramToken').value = '';
      el('telegramStatus').textContent = (data.connected ? 'Đã kết nối @' + data.username : (data.running ? 'Đang kết nối bot' : 'Bot đang tắt')) +
        (data.token_set ? ' · Đã lưu token' : ' · Chưa có token') + (data.error ? ' · ' + data.error : '');
    } catch (e) { el('telegramStatus').textContent = e.message; }
  }
  el('telegramRefresh').onclick = loadTelegram;
  document.querySelector('button[data-t="telegram"]').addEventListener('click', loadTelegram);
  el('telegramSave').onclick = async () => {
    el('telegramSave').disabled = true; el('telegramStatus').textContent = 'Đang lưu và áp dụng…';
    try {
      await api('/v1/telegram/settings', {method:'POST', body: JSON.stringify({enabled:el('telegramEnabled').checked,
        token:el('telegramToken').value, user_ids:el('telegramUserIds').value, send_original:el('telegramOriginal').checked})});
      await loadTelegram();
    } catch (e) { el('telegramStatus').textContent = e.message; }
    finally { el('telegramSave').disabled = false; }
  };
  if (location.hash === '#chat') document.querySelector('button[data-t="chat"]').click();
}

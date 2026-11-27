(() => {
  const list = document.querySelector('#ai-list'), message = document.querySelector('#ai-message');
  const editor = document.querySelector('#ai-editor'), form = document.querySelector('#ai-form');
  let configs = [], editing = null, busy = false, createId = crypto.randomUUID();
  const show = (text) => { message.textContent = text; message.hidden = false; };
  async function request(url, method = 'GET', data) {
    const response = await fetch(url, {method, headers: data ? {'Content-Type':'application/json'} : {}, body: data ? JSON.stringify(data) : undefined});
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(response.status === 401 ? '请先登录角色账号，再管理模型。' : (result.error || '请求未完成，请稍后重试。'));
    return result;
  }
  function button(text, action, item) {
    const el = document.createElement('button'); el.type = 'button'; el.className = 'button secondary'; el.textContent = text;
    el.addEventListener('click', () => action(item)); return el;
  }
  function open(item) {
    editing = item; form.reset(); form.elements.enabled.checked = item ? item.enabled : true;
    for (const field of ['name','base_url','model_id','protocol','expires_on','notes']) form.elements[field].value = item?.[field] || (field === 'protocol' ? 'openai_compatible' : '');
    form.elements.api_key.required = !item; form.elements.api_key.value = '';
    document.querySelector('#ai-editor-title').textContent = item ? '编辑 API 入口' : '添加 API 入口';
    editor.hidden = false; editor.scrollIntoView({behavior:'smooth'}); form.elements.name.focus();
  }
  async function action(item, kind) {
    if (busy) return;
    if (kind === 'delete' && !confirm(`删除「${item.name}」？删除后需重新填写 API Key。`)) return;
    if (kind === 'test' && !confirm('连接测试会发送一条简短测试消息，可能产生费用。继续吗？')) return;
    busy = true; list.setAttribute('aria-busy','true');
    try {
      if (kind === 'edit') { open(item); return; }
      const base = `/api/ai/configs/${item.id}`;
      if (kind === 'delete') await request(base, 'DELETE', {expected_version:item.config_version});
      if (kind === 'default') await request(base+'/default', 'POST', {expected_version:item.config_version});
      if (kind === 'test') await request(base+'/test', 'POST', {expected_version:item.config_version, request_id:crypto.randomUUID()});
      if (kind === 'toggle') await request(base, 'PATCH', {name:item.name,base_url:item.base_url,model_id:item.model_id,protocol:item.protocol,expires_on:item.expires_on,notes:item.notes,enabled:!item.enabled,expected_version:item.config_version});
      show(({delete:'已删除配置。',default:'已设置默认模型。',test:'连接测试成功。',toggle:'启用状态已更新。'})[kind]);
      await load();
    } catch (error) { show(error.message); if (kind === 'test') await load(); }
    finally { busy = false; list.removeAttribute('aria-busy'); }
  }
  function render() {
    list.replaceChildren();
    if (!configs.length) { const empty=document.createElement('p'); empty.className='muted'; empty.textContent='还没有模型入口，可点击上方按钮添加。'; list.append(empty); return; }
    for (const item of configs) {
      const card=document.createElement('article'); card.className='card form-card ai-card';
      const title=document.createElement('h3'); title.textContent=item.name; card.append(title);
      const info=document.createElement('p'); info.className='muted';
      const test = !item.last_test_result ? '尚未测试' : item.test_stale ? '测试结果已过期' : item.last_test_result === 'succeeded' ? '连接成功' : '连接未成功';
      info.textContent=`模型：${item.model_id} · ${item.enabled ? '已启用' : '已停用'}${item.is_default ? ' · 默认模型' : ''} · 到期：${item.expires_on || '未填写'} · ${test}`; card.append(info);
      const key=document.createElement('p'); key.className='muted'; key.textContent=`API Key：${item.api_key_masked || '未设置'}`; card.append(key);
      const actions=document.createElement('div'); actions.className='form-row';
      actions.append(button('编辑', x => action(x,'edit'),item), button(item.enabled ? '停用' : '启用', x => action(x,'toggle'),item));
      if (item.enabled && !item.is_default) actions.append(button('设为默认', x => action(x,'default'),item));
      if (item.enabled) actions.append(button('测试连接', x => action(x,'test'),item));
      actions.append(button('删除', x => action(x,'delete'),item)); card.append(actions); list.append(card);
    }
  }
  async function load() { try { configs=await request('/api/ai/configs'); render(); } catch(error) { list.replaceChildren(); show(error.message); } }
  document.querySelector('#ai-new').addEventListener('click',()=>{ createId=crypto.randomUUID(); open(null); });
  document.querySelector('#ai-cancel').addEventListener('click',()=>{ form.reset(); editor.hidden=true; });
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (busy) return;
    const data=Object.fromEntries(new FormData(form)); data.enabled=form.elements.enabled.checked; data.expires_on=data.expires_on || null;
    if (!data.api_key) delete data.api_key;
    if (editing && editing.base_url !== data.base_url && !confirm('新地址将收到此配置的 API Key，请确认你信任新服务商。继续吗？')) return;
    if (editing) data.expected_version=editing.config_version; else data.request_id=createId;
    busy=true; form.querySelector('button[type="submit"]').disabled=true;
    try { await request(editing ? `/api/ai/configs/${editing.id}` : '/api/ai/configs',editing ? 'PATCH' : 'POST',data); form.reset(); editor.hidden=true; show('配置已保存。'); await load(); }
    catch(error) { show(error.message); }
    finally { busy=false; form.querySelector('button[type="submit"]').disabled=false; }
  });
  const cloudPanel=document.querySelector('#supabase-detail'),cloudOpen=document.querySelector('#supabase-open');
  const cloudMessage=document.querySelector('#supabase-message');
  let cloud=null;
  document.querySelector('#supabase-card').addEventListener('click',event=>{if(!event.target.closest('button,a'))cloudOpen.click();});
  cloudOpen.addEventListener('click',()=>{
    cloudPanel.hidden=!cloudPanel.hidden;cloudOpen.setAttribute('aria-expanded',String(!cloudPanel.hidden));
    if(!cloudPanel.hidden){cloudPanel.scrollIntoView({behavior:'smooth'});document.querySelector('#supabase-title').focus();}
    if(!cloud)loadCloud();
  });
  document.querySelector('#supabase-close').addEventListener('click',()=>{cloudPanel.hidden=true;cloudOpen.setAttribute('aria-expanded','false');cloudOpen.focus();});
  async function loadCloud(){
    try{
      cloud=await request('/api/ai/supabase');
      document.querySelector('#supabase-status').textContent=`配置状态：${cloud.configured?'已配置':'未配置'}`;
      document.querySelector('#supabase-project-url').value=cloud.project_url || (cloud.project_url_configured?'配置地址无效':'未配置');
      document.querySelector('#supabase-public-key').value=cloud.public_key_configured?`${cloud.public_key_type} · ${cloud.public_key_masked}`:cloud.public_key_invalid?'配置不可用于公开展示':'未配置';
      document.querySelector('#supabase-server-key').textContent=cloud.server_key_configured?'已配置':'未配置';
      document.querySelector('#supabase-bucket').textContent=cloud.storage_bucket_configured?'已配置':'未配置';
      document.querySelector('#supabase-copy-url').disabled=!cloud.project_url;
      document.querySelector('#supabase-copy-key').disabled=!cloud.public_key_configured;
      for(const id of ['#supabase-dashboard','#supabase-dashboard-detail'])document.querySelector(id).href=cloud.dashboard_url;
      cloudMessage.textContent='';
    }catch(error){cloud=null;document.querySelector('#supabase-status').textContent=error.message;cloudMessage.textContent=error.message+' 点击查看配置可重试。';}
  }
  async function copyCloud(kind){
    const control=document.querySelector(kind==='url'?'#supabase-copy-url':'#supabase-copy-key');control.disabled=true;
    try{
      if(!navigator.clipboard?.writeText)throw new Error('当前浏览器不支持剪贴板，请使用本地网址或HTTPS访问。');
      let value=kind==='url'?cloud?.project_url:null;
      if(kind==='key')value=(await request('/api/ai/supabase/public-key/copy','POST',{})).public_key;
      if(!value)throw new Error('此字段未配置。');
      await navigator.clipboard.writeText(value);value=null;
      cloudMessage.textContent=kind==='url'?'Project URL 已复制。':'公开 API Key 已复制。';
    }catch(error){cloudMessage.textContent=error.message;}
    finally{control.disabled=kind==='url'?!cloud?.project_url:!cloud?.public_key_configured;}
  }
  document.querySelector('#supabase-copy-url').addEventListener('click',()=>copyCloud('url'));
  document.querySelector('#supabase-copy-key').addEventListener('click',()=>copyCloud('key'));
  loadCloud();
  load();
})();

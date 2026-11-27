(() => {
  const root = document.querySelector('.life-os-page');
  const dateNode = document.getElementById('life-os-date');
  const timeNode = document.getElementById('life-os-time');
  if (!root || !dateNode || !timeNode) return;

  const requestedZone = root.dataset.timezone;
  let zone = requestedZone;
  try {
    new Intl.DateTimeFormat('zh-CN', { timeZone: zone }).format(new Date());
  } catch (_) {
    zone = undefined;
  }
  const dateFormat = new Intl.DateTimeFormat('zh-CN', {
    timeZone: zone, year: 'numeric', month: 'long', day: 'numeric', weekday: 'long'
  });
  const timeFormat = new Intl.DateTimeFormat('zh-CN', {
    timeZone: zone, hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
  });

  function renderClock() {
    const now = new Date();
    dateNode.dateTime = now.toISOString();
    dateNode.textContent = dateFormat.format(now);
    timeNode.textContent = timeFormat.format(now);
  }

  renderClock();
  window.setInterval(renderClock, 1000);

  const form = document.getElementById('life-os-form');
  if (!form) return;
  const feedback = document.getElementById('life-os-feedback');
  const history = document.getElementById('life-os-history');
  const stateBox = document.getElementById('life-os-state');
  const input = document.getElementById('life-os-input');
  const consent = document.getElementById('life-os-consent');
  const send = document.getElementById('life-os-send');
  const more = document.getElementById('life-os-more');
  const errors = {no_model:'请先在灵石区设置默认模型。',upstream_timeout:'模型超时；原文与旧分析保留，可手动重试。',output_truncated:'模型输出被截断；旧分析保留。',invalid_json:'模型未返回完整 JSON；旧分析保留。',invalid_schema:'模型字段校验失败；旧分析保留。',interrupted:'上次分析中断，可手动重试。',unauthorized:'请先登录角色账号。'};
  let busy = false, pendingSave = null, expanded = false;
  function node(tag, text, cls) { const n = document.createElement(tag); if(text !== undefined)n.textContent=text; if(cls)n.className=cls; return n; }
  async function api(path, data, method = data ? 'POST' : 'GET') {
    const request=()=>fetch('/api/life-os'+path, {method,headers:data ? {'Content-Type':'application/json'} : {},body:data ? JSON.stringify(data) : undefined});
    const response = await (path.endsWith('/analyze') ? window.lifeOSAI(request) : request());
    const result = await response.json();
    if (!response.ok) throw new Error(errors[result.code] || result.error || '请求失败，请稍后重试。');
    return result;
  }
  function setBusy(value) {busy=value;send.disabled=value;more.disabled=value;history.querySelectorAll('button').forEach(b=>b.disabled=value);stateBox.querySelectorAll('button').forEach(b=>b.disabled=value);}
  function showState(snapshot) {
    stateBox.replaceChildren();
    for (const [id,key] of [['life-layers','life_layers'],['need-layers','need_layers']]) {
      const selected = snapshot?.result?.[key] || [];
      document.querySelectorAll('#'+id+' li').forEach(item => item.classList.toggle('is-highlighted', selected.includes(item.querySelector('button')?.dataset.layer || item.textContent.trim())));
    }
    document.getElementById('layer-summary').textContent = snapshot ? '已根据最近一次分析标记相关层次；点击层次查看和管理个人经验。' : '尚无分析结果；点击层次仍可管理个人经验。';
    document.getElementById('layer-conflict').textContent = snapshot?.result?.core_conflict ? '本轮核心矛盾：' + snapshot.result.core_conflict : '';
    if(!snapshot)return;
    const title=node('h3','当前状态 · 可手动校准');stateBox.append(title);
    const f=node('form');f.className='life-os-calibration';
    for (const [key,label] of [['energy','心理能量'],['bandwidth','心理带宽'],['order','生活秩序']]) {
      const value=snapshot.result[key];const l=node('label',label);const i=node('input');i.name=key;i.type='number';i.min='0';i.max='100';i.step='1';i.value=value.value??'';i.placeholder='未知';l.append(i,node('small',value.reason));f.append(l);
    }
    const b=node('button','保存校准');b.type='submit';b.className='button secondary';f.append(b);let requestId=null;
    f.addEventListener('input',()=>{requestId=null;});
    f.addEventListener('submit',async event=>{event.preventDefault();if(busy)return;setBusy(true);try{const data={request_id:requestId||=crypto.randomUUID()};for(const k of ['energy','bandwidth','order'])data[k]=f.elements[k].value===''?null:Number(f.elements[k].value);await api('/analyses/'+snapshot.id+'/state',data);await load();feedback.textContent='状态校准已保存。';}catch(e){feedback.textContent=e.message;}finally{setBusy(false);}});
    stateBox.append(f);
  }

  function historyAction(text, handler, danger=false) {
    const button=node('button',text,'life-history-action'+(danger?' life-history-delete':''));
    button.type='button';
    button.addEventListener('click',handler);
    return button;
  }

  function editHistory(item, area) {
    if(busy||area.childElementCount)return;
    const editor=node('form',undefined,'form-stack');
    const text=node('textarea');
    text.setAttribute('aria-label','编辑历史原文');
    text.rows=4;
    text.maxLength=Math.max(4000,item.content.length);
    text.value=item.content;
    text.required=true;
    const submit=node('button','保存修改','button primary');
    submit.type='submit';
    editor.append(text,node('small','修改原文后，引用这段文字的旧分析会清除，可重新分析。'),
      submit,historyAction('取消',()=>area.replaceChildren()));
    editor.addEventListener('submit',async event=>{
      event.preventDefault();
      if(busy||!text.value.trim())return;
      setBusy(true);
      try {
        await api('/messages/'+item.id,{content:text.value},'PATCH');
        await load();
        feedback.textContent='历史原文已更新，可重新分析。';
      } catch(e) { feedback.textContent=e.message; }
      finally { setBusy(false); }
    });
    area.append(editor);
    text.focus();
  }

  async function deleteHistory(item) {
    if(busy||!confirm('确定删除这条原文？引用它的分析及由它提供的事件依据也会移除。'))return;
    setBusy(true);
    try {
      await api('/messages/'+item.id,null,'DELETE');
      await load();
      feedback.textContent='历史记录已删除。';
    } catch(e) { feedback.textContent=e.message; }
    finally { setBusy(false); }
  }
  function renderItem(item) {
    const box=node('article',undefined,'life-os-message');box.dataset.messageId=item.id;
    const header=node('div',undefined,'life-history-header'), actions=node('div',undefined,'life-history-actions'), editor=node('div');
    actions.append(historyAction('编辑',()=>editHistory(item,editor)),historyAction('删除',()=>deleteHistory(item),true));
    header.append(node('small',new Intl.DateTimeFormat('zh-CN',{timeZone:zone,dateStyle:'medium',timeStyle:'short'}).format(new Date(item.created_at))),actions);
    box.append(header,node('p',item.content,'life-os-original'),editor);
    if(item.analysis){
      const r=item.analysis.result;box.append(node('p',r.reply,'life-os-reply'));
      const d=node('details');d.append(node('summary','查看本轮分析'));
      for(const [key,label] of [['core_conflict','核心矛盾'],['triggers','诱因'],['likely_behaviors','可能行为（预测）'],['behavior_contribution','行为可能带来的帮助'],['ideal_solution','长远方案'],['feasible_action','当下可执行动作'],['life_layers','人生层次'],['need_layers','需要层次'],['suggested_mode','建议模式']]) {const v=r[key];const modes={green:'发展',yellow:'稳定',red:'维持',blue:'重启',unknown:'信息不足'};d.append(node('p',label+'：'+(Array.isArray(v)?v.join('、')||'暂无':key==='suggested_mode'?modes[v]:v||'暂无')));}box.append(d);
    }
    if(item.analysis?.experience_status==='failed')box.append(node('p','该轮核心分析已保存，问题经验更新失败，可手动重新分析。','life-os-error'));
    const status=item.attempt?.status;
    if(status==='failed')box.append(node('p',errors[item.attempt.error_code]||'分析失败（'+item.attempt.error_code+'），原文和旧分析保留。','life-os-error'));
    if(status==='running')box.append(node('p','分析处理中；可稍后刷新读取。'));
    if(status!=='running') {const b=node('button',item.analysis?'重新分析':'分析 / 重试');b.type='button';b.className='button secondary';b.addEventListener('click',()=>runAnalysis(item.id));box.append(b);}
    const versions=node('details');versions.append(node('summary','分析与校准历史'));
    const list=node('div');const read=node('button','读取历史');read.type='button';read.className='button secondary';let offset=0;
    read.addEventListener('click',async()=>{read.disabled=true;try{const data=await api('/messages/'+item.id+'/analyses?offset='+offset);for(const v of data.items){list.append(node('p',new Intl.DateTimeFormat('zh-CN',{timeZone:zone,dateStyle:'short',timeStyle:'short'}).format(new Date(v.created_at))+' · '+(v.status==='succeeded'?v.result.reply:'分析状态：'+v.status+' / '+(v.error_code||''))));if(v.result)for(const k of ['energy','bandwidth','order'])list.append(node('small',({energy:'能量',bandwidth:'带宽',order:'秩序'}[k])+': '+(v.result[k].value??'未知')+' · '+v.result[k].reason+' '));}offset=data.next_offset;read.hidden=offset===null;}catch(e){feedback.textContent=e.message;}finally{read.disabled=false;}});
    versions.append(list,read);box.append(versions);history.append(box);
  }

  async function load() {
    const data=await api('/messages?limit='+(expanded?50:3));
    const items=[...data.items];
    let offset=data.next_offset;
    while(expanded&&offset!==null){
      const page=await api('/messages?limit=50&offset='+offset);
      items.push(...page.items);offset=page.next_offset;
    }
    history.replaceChildren();
    showState(data.state);
    window.dispatchEvent(new Event('life-os-updated'));
    items.forEach(renderItem);
    more.hidden=items.length<=3&&data.next_offset===null;
    more.textContent=expanded?'收起历史':'查看更多';
    more.setAttribute('aria-expanded',String(expanded));
    if(!items.length)history.append(node('p','尚无对话。从上面记录一件正在发生的事情。'));
  }
  async function runAnalysis(id) {if(busy)return;if(!consent.checked){feedback.textContent='请先勾选发送近期对话给模型的授权。';return;}setBusy(true);feedback.textContent='原文已保存，正在分析…';try{const result=await api('/messages/'+id+'/analyze',{request_id:crypto.randomUUID(),consent_external:true,note_ids:[...document.querySelectorAll('.life-note-select:checked')].map(x=>x.value)});await load();feedback.textContent=result.status==='succeeded'?(result.experience_status==='failed'?'核心分析已保存；问题经验更新失败（'+result.experience_error+'），可手动重新分析。':result.experience_status==='pending'?'分析已保存，事件归属待确认。':'分析已保存。'):'本次分析状态：'+result.status;}catch(e){feedback.textContent=e.message;try{await load();}catch(_){} }finally{setBusy(false);}}
  form.addEventListener('submit',async event=>{event.preventDefault();if(busy)return;const text=input.value;const noteIds=[...document.querySelectorAll('.life-note-select:checked')].map(x=>x.value);if(!text.trim()&&!noteIds.length){feedback.textContent='请填写想说的话或勾选杂念。';return;}if(!consent.checked){feedback.textContent='请先确认模型分析授权。';return;}setBusy(true);feedback.textContent='正在保存原文…';try{if(!pendingSave||pendingSave.content!==text||JSON.stringify(pendingSave.note_ids)!==JSON.stringify(noteIds))pendingSave={request_id:crypto.randomUUID(),content:text,note_ids:noteIds};const saved=await api('/messages',pendingSave);pendingSave=null;input.value='';await load();setBusy(false);await runAnalysis(saved.id);}catch(e){feedback.textContent=e.message;}finally{setBusy(false);}});
  more.addEventListener('click',async()=>{if(busy)return;setBusy(true);expanded=!expanded;try{await load();}catch(e){expanded=!expanded;feedback.textContent=e.message;}finally{setBusy(false);}});
  load().catch(e=>{feedback.textContent=e.message;});
})();

(() => {
 const params=new URLSearchParams(location.search);if(!params.get('task_id'))return;
 const panel=document.querySelector('#breakdown-workspace'),message=document.querySelector('#breakdown-message'),editor=document.querySelector('#breakdown-editor'),history=document.querySelector('#breakdown-history'),mode=document.querySelector('#breakdown-mode');
 const feedback=document.querySelector('#breakdown-feedback'),generateButton=document.querySelector('#breakdown-generate'),confirmButton=document.querySelector('#breakdown-confirm');
 let plan=null,busy=false,dirty=false,booted=false,pending=null,offset=null,reading=0;
 const labels={tasks:'保存为副本 / 子任务',milestones:'保存为里程碑',checklist:'保存为行动清单'};
 const states={draft:'待确认',confirmed:'已保存',generating:'生成中',failed:'生成失败',superseded:'已有新版'};
 async function api(url,method='GET',data){const r=await fetch(url,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});const result=await r.json();if(!r.ok){const error=Error(result.error||'暂时无法完成，请稍后重试');error.status=r.status;throw error;}return result;}
 function el(tag,text='',cls=''){const node=document.createElement(tag);node.textContent=text;if(cls)node.className=cls;return node;}
 function controls(){panel.querySelectorAll('button,input,textarea,select').forEach(x=>x.disabled=busy);confirmButton.disabled=busy||dirty||plan?.stale;}
 function edited(){dirty=true;message.textContent='有未保存的修改，请先保存草稿修改。';controls();}
 function field(parent,label,value,type='text',key=''){const wrap=el('label',label),input=el(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;input.value=value;input.dataset.field=key;input.addEventListener('input',edited);wrap.append(input);parent.append(wrap);return input;}
 function activeSteps(){return plan?.advice?.steps.filter(s=>s.id in plan.mapping||s.id in plan.checklist)||[];}
 function startLabel(){if(!plan)return;const first=firstStep();const mapped=plan.mapping[first?.id];const existing=document.querySelector('#breakdown-existing').value;document.querySelector('#breakdown-start').textContent=plan.target.kind==='quest'&&mapped?.kind!=='task'&&!existing?'确认创建第一步副本并进入专注':'进入第一步专注';}
 function firstStep(){const saved=activeSteps();return saved.find(s=>s.id===plan?.advice?.minimum_id)||saved[0];}
 function render(value){
  plan=value;dirty=false;editor.replaceChildren();document.querySelector('#breakdown-advice').replaceChildren();
  document.querySelector('#breakdown-reply').textContent=plan.advice?.reply||'';
  const state=plan.based_on_state===undefined?plan.target.state:plan.based_on_state;document.querySelector('#breakdown-state').textContent=state?`方案生成时的已确认状态：压力 ${state.pressure} · 能量 ${state.energy} · ${state.difficulty}`:'尚无确认状态；可先使用左侧滑杆记录。';
  const failures={upstream_timeout:'模型响应超时，旧方案仍保留，可重新生成。',invalid_output:'模型返回格式不符合要求，旧方案仍保留，请重新生成。',stale:'目标、状态或草稿已变化，请重新读取后再生成。',no_model:'请先在灵石区配置可用的拆解模型。'};
  message.textContent=plan.status==='failed'?(failures[plan.error_code]||'生成未成功，旧方案仍保留。请检查模型后重新生成。'):plan.stale&&plan.status==='draft'?'目标或状态已变化，请重新生成方案。':plan.stale&&plan.status==='confirmed'?'已保存的历史方案；目标或状态有变化，可重新拆解。':states[plan.status]||'';
  const draft=plan.status==='draft',confirmed=plan.status==='confirmed';
  const minimumStep=confirmed?firstStep():plan.advice?.steps.find(s=>s.id===plan.advice.minimum_id);const minimumBox=document.querySelector('#breakdown-minimum');minimumBox.hidden=!minimumStep;if(minimumStep)minimumBox.textContent=`现在只做这一步就可以：${minimumStep.title} · 预计 ${minimumStep.minutes} 分钟（估计） · ${minimumStep.done_when}`;
  document.querySelector('#breakdown-edit').hidden=!draft;document.querySelector('#breakdown-save').hidden=!draft;document.querySelector('#breakdown-execution').hidden=!confirmed;
  mode.replaceChildren();for(const key of plan.target.modes){const option=el('option',labels[key]);option.value=key;mode.append(option);}
  generateButton.textContent=confirmed?'结合反馈生成新方案':'重新拆解 / 根据反馈调整';
  for(const step of plan.advice?.steps||[]){
   if(confirmed&&!(step.id in plan.mapping)&&!(step.id in plan.checklist))continue;
   const card=el('article','', 'breakdown-step');card.dataset.stepId=step.id;
   if(draft){
    const selected=el('input');selected.type='checkbox';selected.checked=true;selected.dataset.selected='true';const selectLabel=el('label','保存这一步');selectLabel.prepend(selected);card.append(selectLabel);
    const minimum=el('input');minimum.type='radio';minimum.name='minimum-step';minimum.value=step.id;minimum.checked=step.id===plan.advice.minimum_id;minimum.addEventListener('change',edited);const minimumLabel=el('label','作为最小启动动作');minimumLabel.prepend(minimum);card.append(minimumLabel);
    field(card,'行动',step.title,'text','title').maxLength=160;field(card,'说明',step.detail,'textarea','detail').maxLength=600;
    const minutes=field(card,'预计分钟（估计）',step.minutes,'number','minutes');minutes.min=1;minutes.max=240;
    field(card,'完成标志',step.done_when,'textarea','done_when').maxLength=200;
    const reuse=el('select');reuse.dataset.reuse='true';const none=el('option','新建这一步');none.value='';reuse.append(none);
    for(const obj of plan.target.existing.filter(x=>x.status!=='completed')){const option=el('option','复用：'+obj.title+(obj.kind==='milestone'?'（里程碑）':'（副本）'));option.value=obj.id;option.dataset.kind=obj.kind;reuse.append(option);}
    const reuseLabel=el('label','已有内容');reuseLabel.append(reuse);card.append(reuseLabel);
   }else{
    card.append(el('h3',step.title+(step.id===plan.advice.minimum_id?' · 现在先做这一步':'')),el('p',step.detail),el('p',`预计 ${step.minutes} 分钟 · 完成标志：${step.done_when}`));
    const mapped=plan.mapping[step.id];if(mapped){const link=el('a',mapped.reused?'查看已复用项目':'查看已保存项目','text-link');link.href=mapped.kind==='task'?'/tasks/'+mapped.id:plan.target.href;card.append(link);}
    if(step.id in plan.checklist){const check=el('input');check.type='checkbox';check.checked=plan.checklist[step.id];const label=el('label','清单完成');label.prepend(check);card.append(label);check.addEventListener('change',()=>mutate('/'+plan.id+'/checklist','PATCH',{request_id:crypto.randomUUID(),expected_version:plan.checklist_version,step_id:step.id,checked:check.checked}));}
   }
   editor.append(card);
  }
  if(plan.advice?.state_advice?.ready&&draft&&!plan.stale){const box=document.querySelector('#breakdown-advice');box.append(el('p','你提到了状态变化。以下为待确认建议：'+plan.advice.state_advice.reply));const button=el('button','载入新的状态建议','button secondary');button.type='button';button.addEventListener('click',()=>window.dispatchEvent(new CustomEvent('state-advice',{detail:{plan_id:plan.id,base_generation:plan.target.generation,response:plan.advice.state_advice}})));box.append(button);}
  const existing=document.querySelector('#breakdown-existing');existing.replaceChildren();const none=el('option','按所选方案执行');none.value='';existing.append(none);
  for(const t of plan.target.existing.filter(x=>x.kind==='task'&&x.status!=='completed')){const option=el('option',t.title);option.value=t.id;existing.append(option);}
  existing.parentElement.hidden=plan.target.kind!=='quest'||plan.save_mode==='tasks';startLabel();controls();
 }
 async function histories(append=false){const data=await api('/api/startup/breakdowns?'+new URLSearchParams({task_type:params.get('task_type'),task_id:params.get('task_id'),offset:append?offset||0:0}));if(!append)history.replaceChildren();for(const p of data.items){const option=el('option',`${states[p.status]} · ${new Date(p.created_at).toLocaleString()}${p.feedback?' · '+p.feedback.slice(0,18):''}`);option.value=p.id;history.append(option);}offset=data.next_offset;document.querySelector('#breakdown-more').hidden=offset===null;if(plan)history.value=plan.id;return data.items;}
 async function reload(){const seq=++reading;if(busy)return;try{const values=await histories();if(seq!==reading)return;const item=plan?values.find(x=>x.id===plan.id):values[0];if(item)render(item);else if(!plan){editor.replaceChildren();generateButton.textContent='生成拆解方案';}}catch(e){message.textContent=e.message;}}
 async function mutate(path,method,data){if(busy)return;busy=true;controls();try{render(await api('/api/startup/breakdowns'+path,method,data));await histories();window.dispatchEvent(new Event('recommendations-refreshed'));}catch(e){message.textContent=e.message;}finally{busy=false;controls();}}
 async function generate(requestId=null){if(busy)return;if(dirty){message.textContent='请先保存草稿修改，或重新读取后再生成。';return;}busy=true;controls();message.textContent='正在为这个目标生成小步骤……';
  const previous=plan&&['draft','confirmed'].includes(plan.status)?plan:null;
  const data={task_type:params.get('task_type'),task_id:params.get('task_id'),previous_id:previous?.id||null,expected_revision:previous?.revision||null,feedback:feedback.value};
  if(!pending||JSON.stringify(pending.data)!==JSON.stringify(data))pending={data,request_id:requestId||crypto.randomUUID()};
  try{const value=await api('/api/startup/breakdowns','POST',{...pending.data,request_id:pending.request_id});pending=null;params.delete('generate');const cleanURL=new URL(location.href);cleanURL.searchParams.delete('generate');window.history.replaceState(null,'',cleanURL);render(value);await histories();if(value.status==='draft')feedback.value='';}
  catch(e){message.textContent=e.message;if(e.status)pending=null;}finally{busy=false;controls();}
 }
 document.querySelector('#breakdown-feedback-form').addEventListener('submit',e=>{e.preventDefault();generate();});
 document.querySelector('#breakdown-edit').addEventListener('click',()=>{const steps=[...editor.querySelectorAll('[data-step-id]')].map(card=>{const fields=Object.fromEntries([...card.querySelectorAll('[data-field]')].map(x=>[x.dataset.field,x.dataset.field==='minutes'?Number(x.value):x.value]));return {id:card.dataset.stepId,...fields};});const minimum=editor.querySelector('input[name="minimum-step"]:checked');mutate('/'+plan.id,'PATCH',{expected_revision:plan.revision,steps,minimum_id:minimum?.value});});
 confirmButton.addEventListener('click',()=>{const cards=[...editor.querySelectorAll('[data-step-id]')].filter(x=>x.querySelector('[data-selected]').checked);const reuse={};for(const card of cards){const select=card.querySelector('[data-reuse]');if(mode.value!=='checklist'&&select.value){const kind=select.selectedOptions[0].dataset.kind;if(kind!==(mode.value==='milestones'?'milestone':'task')){message.textContent='复用对象类型与保存方式不匹配，请重新选择。';return;}reuse[card.dataset.stepId]=select.value;}}mutate('/'+plan.id+'/confirm','POST',{expected_revision:plan.revision,selected:cards.map(x=>x.dataset.stepId),mode:mode.value,reuse,allow_duplicates:document.querySelector('#breakdown-duplicates').checked,confirmed:true});});
 document.querySelector('#breakdown-existing').addEventListener('change',startLabel);
 document.querySelector('#breakdown-start').addEventListener('click',async()=>{if(busy||!firstStep())return;busy=true;controls();try{const step=firstStep(),existing=document.querySelector('#breakdown-existing').value;const result=await api('/api/startup/breakdowns/'+plan.id+'/start','POST',{step_id:step.id,existing_task_id:existing||null,create_task:plan.target.kind==='quest'&&plan.mapping[step.id]?.kind!=='task'&&!existing});location.assign(result.href);}catch(e){message.textContent=e.message;}finally{busy=false;controls();}});
 history.addEventListener('change',async()=>{if(busy)return;busy=true;controls();try{render(await api('/api/startup/breakdowns/'+history.value));pending=null;}catch(e){message.textContent=e.message;}finally{busy=false;controls();}});
 document.querySelector('#breakdown-more').addEventListener('click',()=>histories(true).catch(e=>message.textContent=e.message));
 document.querySelector('#breakdown-reload').addEventListener('click',reload);
 document.querySelector('#breakdown-state-toggle').addEventListener('click',()=>{const box=document.querySelector('#state-chat-content');box.hidden=!box.hidden;if(!box.hidden)box.scrollIntoView({behavior:'smooth'});});
 window.addEventListener('breakdown-target',async()=>{panel.hidden=false;if(booted)return;booted=true;document.querySelector('#state-chat-content').hidden=true;await reload();const nonce=params.get('generate');if(nonce&&/^[0-9a-f-]{36}$/i.test(nonce)){// Replay the same navigation request, never generate on ordinary reload.
    plan=null;await generate(nonce);
   }});
 window.addEventListener('breakdown-unavailable',()=>{panel.hidden=true;});
 window.addEventListener('state-saved',()=>{if(plan?.status==='draft'){plan.stale=true;message.textContent='状态已更新，请重新拆解。';controls();}});
 setInterval(()=>{if(!document.hidden&&!busy&&plan?.status==='generating')reload();},5000);
})();

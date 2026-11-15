(() => {
 const form=document.querySelector('#chat-form'),input=document.querySelector('#chat-input'),status=document.querySelector('#chat-status'),list=document.querySelector('#chat-messages'),select=document.querySelector('#chat-conversations');
 const more=document.querySelector('#chat-more'),newButton=document.querySelector('#chat-new'),moreChats=document.querySelector('#chat-more-conversations');
 let cid=null,version=0,busy=true,pending=null,before=null,chatOffset=null,reading=0;
 async function api(url,method='GET',data){const r=await fetch(url,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});const value=await r.json();if(!r.ok){const e=Error(value.error||'暂不可用，请稍后再试');e.status=r.status;throw e;}return value;}
 function element(tag,text,cls){const el=document.createElement(tag);el.textContent=text;if(cls)el.className=cls;return el;}
 function controls(){form.querySelectorAll('button,textarea').forEach(x=>x.disabled=busy);select.disabled=busy;newButton.disabled=busy;more.disabled=busy;moreChats.disabled=busy;}
 function row(turn,currentVersion){
  const box=element('article','', 'chat-turn');box.dataset.turnId=turn.id;
  box.append(element('small',new Date(turn.created_at).toLocaleString()),element('p','你：'+turn.message,'chat-user'));
  if(turn.status==='succeeded'&&turn.response){
   const answer=turn.response;box.append(element('p','AI：'+answer.reply,'chat-answer'));
   if(answer.barrier)box.append(element('p','可能的阻力：'+answer.barrier,'muted'));
   if(answer.goal)box.append(element('p','你想达成：'+answer.goal,'muted'));
   if(answer.ready){
    const quadrant=answer.energy>=50?(answer.pressure<50?'投入区':'降噪区'):(answer.pressure<50?'激活区':'修复区');
    box.append(element('p',`建议值 · ${quadrant} · 压力 ${answer.pressure} / 能量 ${answer.energy}。${answer.difficulty}`));
    if(turn.sequence===currentVersion){const apply=element('button','载入建议，调整后确认','button secondary');apply.type='button';apply.disabled=busy;
     apply.addEventListener('click',()=>window.dispatchEvent(new CustomEvent('state-advice',{detail:turn})));box.append(apply);}
   }
  }else{const errors={no_model:'请先到灵石区设置默认模型。',rate_limit:'模型正在处理其他请求或调用频繁，请稍后再发送。',invalid_output:'模型返回格式不符合要求，请重新发送。',upstream_timeout:'模型响应超时；本次结果未知，不会自动重发。',interrupted:'请求已中断，请重新发送。'};box.append(element('p',turn.status==='pending'?'等待回复。可稍后重读对话；超过两分钟仍无回复时可重新发送。':(errors[turn.error_code]||'本次模型调用未成功，请检查灵石区配置后重新发送。'),'muted'));}
  return box;
 }
 async function loadHistory(older=false){
  if(!cid)return;const target=cid,seq=++reading;
  const data=await api('/api/startup/chat/conversations/'+cid+(older&&before?'?before='+before:''));
  if(cid!==target||seq!==reading)return;
  version=data.version;before=data.next_before;more.hidden=before===null;
  if(!older)list.replaceChildren();
  const fragment=document.createDocumentFragment();data.items.forEach(t=>fragment.append(row(t,data.version)));
  if(older)list.prepend(fragment);else list.append(fragment);
 }
 async function conversations(append=false){
  const data=await api('/api/startup/chat/conversations?offset='+(append?chatOffset||0:0));
  if(!append)select.replaceChildren(element('option','新的状态对话'));
  select.options[0].value='';
  for(const item of data.items){const option=element('option',item.title);option.value=item.id;select.append(option);}
  chatOffset=data.next_offset;moreChats.hidden=chatOffset===null;
  if(cid&&!Array.from(select.options).some(x=>x.value===cid)){const option=element('option','当前对话');option.value=cid;select.append(option);}
  select.value=cid||'';return data.items;
 }
 function reset(){++reading;cid=null;version=0;pending=null;before=null;select.value='';list.replaceChildren();more.hidden=true;status.textContent='新的状态对话。';window.dispatchEvent(new Event('manual-state'));}
 newButton.addEventListener('click',reset);
 select.addEventListener('change',async()=>{if(!select.value){reset();return;}++reading;cid=select.value;pending=null;list.replaceChildren();busy=true;controls();try{await loadHistory();status.textContent='已载入对话历史。';}catch(e){status.textContent=e.message;}finally{busy=false;controls();list.querySelectorAll('button').forEach(x=>x.disabled=false);}});
 more.addEventListener('click',()=>loadHistory(true).catch(e=>status.textContent=e.message));
 moreChats.addEventListener('click',()=>conversations(true).catch(e=>status.textContent=e.message));
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy||!input.value.trim())return;
  busy=true;controls();list.querySelectorAll('button').forEach(x=>x.disabled=true);status.textContent='正在理解你的描述……';
  if(!pending||pending.message!==input.value.trim())pending={request_id:crypto.randomUUID(),conversation_id:cid,expected_version:version,message:input.value.trim()};
  try{
   const turn=await api('/api/startup/chat/messages','POST',pending);cid=turn.conversation_id;version=turn.sequence;pending=null;
   if(turn.status==='succeeded')input.value='';
   await conversations();await loadHistory();
   status.textContent=turn.status==='succeeded'?'建议已保存到对话中，当前状态还没有改变。':turn.status==='pending'?'请求仍在处理中，请稍后重读历史。':'本次没有获得建议，消息已保存。可重新发送。';
  }catch(e){status.textContent=e.message;if(e.status){pending=null;if(cid)await loadHistory().catch(()=>{});}}
  finally{busy=false;controls();list.querySelectorAll('button').forEach(x=>x.disabled=false);}
 });
 async function refreshHistory(){if(cid&&!busy)await loadHistory();}
 window.addEventListener('focus',()=>refreshHistory().catch(()=>{}));
 setInterval(()=>{if(!document.hidden)refreshHistory().catch(()=>{});},15000);
 let stateOffset=null,stateRead=0;
 const history=document.querySelector('#state-history'),historyMore=document.querySelector('#state-history-more');
 async function states(append=false){const seq=++stateRead;try{const data=await api('/api/startup/history?offset='+(append?stateOffset||0:0));if(seq!==stateRead)return;if(!append)history.replaceChildren();for(const item of data.items)history.append(element('p',`${new Date(item.created_at).toLocaleString()} · ${item.quadrant} · 压力 ${item.pressure} / 能量 ${item.energy} · ${(item.source_turn_id||item.source_plan_id)?'AI 建议经你确认':'手动确认'}${item.difficulty?' · '+item.difficulty:''}`));if(!data.items.length&&!append)history.append(element('p','还没有状态记录。'));stateOffset=data.next_offset;historyMore.hidden=stateOffset===null;}catch(e){if(seq===stateRead&&!append)history.textContent=e.message;}}
 historyMore.addEventListener('click',()=>states(true));window.addEventListener('state-saved',()=>states());
 window.addEventListener('recommendations-view',event=>{
  const target=document.querySelector('#chat-top-tasks'),data=event.detail;target.replaceChildren();target.dataset.batchId=data.batch_id||'';
  const selected=(data.items||[]).filter(x=>!x.stale&&x.level==='green').slice(0,3);
  if(!selected.length){target.append(element('p',data.items?.length?'当前没有绿色推荐。可以休息、调整状态，或自主选择其他任务。':data.message||'确认状态并刷新象限后，这里将显示建议。'));return;}
  for(const item of selected){const block=element('p',''),link=element('a',item.keyword);link.href=item.href;block.append(link,element('span',' · '+item.reason));target.append(block);}
 });
 async function init(){controls();try{const items=await conversations();if(items.length){cid=items[0].id;select.value=cid;await loadHistory();}}catch(e){status.textContent=e.message;}finally{busy=false;controls();list.querySelectorAll('button').forEach(x=>x.disabled=false);}}
 init();states();
})();

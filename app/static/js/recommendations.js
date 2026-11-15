(() => {
 const list=document.querySelector('#recommend-list'), message=document.querySelector('#recommend-message'), button=document.querySelector('#recommend-refresh');
 async function api(url,method='GET',data) { const r=await fetch(url,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined}); const value=await r.json();if(!r.ok){const error=Error(value.error||'请求失败，请稍后重试');error.code=value.code;throw error;}return value; }
 function render(data) {
  if(lastFailure&&data.batch_id&&data.batch_id!==failureBatchId)lastFailure='';
  lastBatchId=data.batch_id||null;
  list.replaceChildren();message.textContent=lastFailure||data.message;window.dispatchEvent(new CustomEvent('recommendations-view',{detail:data}));
  document.querySelectorAll('.quadrant .recommend-tags').forEach(x=>x.remove());
  ['投入区','降噪区','激活区','修复区'].forEach((q,index)=>{const tags=document.createElement('div');tags.className='recommend-tags';for(const item of data.items.filter(x=>!x.stale&&x.analysis_status!=='pending'&&x.quadrants.includes(q))){const a=document.createElement('a');a.href=item.href;a.textContent=item.keyword;a.title=item.reason;tags.append(a);}document.querySelectorAll('.quadrant')[index].append(tags);});
  for(const quadrant of ['投入区','降噪区','激活区','修复区','待确认']) {
   const section=document.createElement('section'),h=document.createElement('h3');h.textContent=quadrant;section.append(h);
   for(const item of data.items.filter(x=>quadrant==='待确认' ? x.stale||!x.quadrants.length : !x.stale&&x.quadrants.includes(quadrant))) {
    const row=document.createElement('p'),link=document.createElement('a');link.textContent=item.keyword;link.href=item.href;link.className='task-title';row.append(link);
    const reason=document.createElement('span');reason.textContent=' · '+(item.stale?'已过期，请刷新':item.reason);row.append(reason);
    if(!item.stale&&item.analysis_status==='pending'&&item.error_code!=='insufficient_information'){const retry=document.createElement('button');retry.type='button';retry.className='button secondary';retry.textContent='单独重试';retry.addEventListener('click',()=>refresh(item.key));row.append(retry);}
    if(!item.stale&&item.analysis_status!=='pending'&&item.analysis_id) {const edit=document.createElement('button');edit.type='button';edit.className='button secondary';edit.textContent='修正象限';edit.addEventListener('click',async()=>{
     const selected=prompt('输入象限：投入区、降噪区、激活区或修复区',item.quadrants[0]||'投入区');if(selected===null)return;if(!['投入区','降噪区','激活区','修复区'].includes(selected)){message.textContent='请输入一个有效象限';return;}
     try{await api('/api/startup/task-analyses/'+item.analysis_id,'PATCH',{expected_version:item.analysis_version,keyword:item.keyword,quadrants:[selected]});message.textContent='已修正，请点击刷新任务结果';}catch(e){message.textContent=e.message;}
    });row.append(edit);}section.append(row);
   }list.append(section);
  }
 }
 let readVersion=0,refreshing=false,lastFailure='',lastBatchId=null,failureBatchId=null;
 function availability(){button.disabled=refreshing||!window.startupState?.confirmed;}
 window.addEventListener('state-readiness',availability);availability();
 async function load(){if(refreshing)return;const version=++readVersion;try{const data=await api('/api/startup/recommendations');if(version===readVersion)render(data);}catch(e){if(version===readVersion){list.replaceChildren();document.querySelectorAll('.quadrant .recommend-tags').forEach(x=>x.remove());message.textContent='推荐暂不可用，请稍后刷新';window.dispatchEvent(new CustomEvent('recommendations-view',{detail:{items:[],message:'推荐暂不可用，请稍后刷新'}}));}}}
 async function refresh(targetKey=null){
  if(refreshing||!window.startupState?.confirmed)return;
  lastFailure='';++readVersion;refreshing=true;availability();message.textContent=targetKey?'正在重试这项任务……':'正在刷新，请稍候……';
  try{render(await api('/api/startup/refresh','POST',{request_id:crypto.randomUUID(),expected_snapshot_id:window.startupState.snapshotId,target_key:targetKey}));}
  catch(e){const label={upstream_timeout:'模型响应超时',output_truncated:'模型输出被截断',invalid_json:'模型 JSON 不完整',invalid_schema:'模型字段校验失败',invalid_output:'模型响应格式无效',no_model:'模型未配置',recommendation_failed:'推荐计算失败'}[e.code];failureBatchId=lastBatchId;lastFailure=(label||e.message)+'；刷新未完成，请重试';}
  finally{refreshing=false;availability();window.dispatchEvent(new Event('recommendations-refreshed'));await load();if(lastFailure)message.textContent=lastFailure;}
 }
 button.addEventListener('click',()=>refresh());
 window.addEventListener('state-saved',()=>{lastFailure='';load();});
 window.addEventListener('focus',load);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
 setInterval(()=>{if(!document.hidden)load();},30000);
 load();
})();

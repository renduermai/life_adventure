(() => {
 const list=document.querySelector('#recommend-list'), message=document.querySelector('#recommend-message'), button=document.querySelector('#recommend-refresh');
 const scatter=document.querySelector('#task-scatter'), detail=document.querySelector('#scatter-detail');
 const quadrants=['投入区','降噪区','激活区','修复区'];
 const levelNames={green:'适合起步',white:'一般',yellow:'谨慎',red:'建议减负'};
 const detailHint='将鼠标移到任务点上，或用键盘选中任务点，可查看任务详情。';
 function hash(value){let result=2166136261;for(const char of value){result=Math.imul(result^char.charCodeAt(0),16777619);}return result>>>0;}
 function markerDetail(item){
  detail.replaceChildren();
  const heading=document.createElement('strong');heading.textContent=(item.kind==='quest'?'主线 · ':'副本 · ')+(item.title||item.keyword);
  const fields=[['描述',item.description||'暂无描述'],['所属主线',item.main_quest||'独立副本'],['推荐等级',levelNames[item.level]||'待确认'],['推荐理由',item.reason||'暂无理由']];
  detail.append(heading);
  for(const [label,value] of fields){const row=document.createElement('p');row.textContent=label+'：'+value;detail.append(row);}
 }
 function renderScatter(items){
  scatter.replaceChildren();detail.textContent=detailHint;
  const used=quadrants.map(()=>new Set());
  for(const item of [...items].sort((a,b)=>a.key.localeCompare(b.key))){
   if(item.stale||item.analysis_status==='pending'||!item.level||!item.href)continue;
   const quadrant=quadrants.indexOf(item.quadrants?.[0]);if(quadrant<0)continue;
   const slots=used[quadrant],start=hash(item.key)%12;let slot=start;
   while(slots.has(slot)&&slots.size<12)slot=(slot+1)%12;
   if(slots.size===12)continue;slots.add(slot);
   const column=slot%4,row=Math.floor(slot/4);
   const x=(quadrant%2?56:8)+column*12;
   const y=(quadrant<2?20:58)+row*11;
   const marker=document.createElement('a');marker.className='task-marker '+(item.kind==='quest'?'task-marker-quest':'task-marker-task')+' level-'+item.level;
   marker.href=item.href;marker.style.left=x+'%';marker.style.top=y+'%';
   marker.setAttribute('aria-label',(item.kind==='quest'?'主线':'副本')+'：'+(item.title||item.keyword)+'；'+(levelNames[item.level]||'待确认')+'；点击查看详情');
   marker.title=[item.title||item.keyword,item.kind==='quest'?'主线':'副本','描述：'+(item.description||'暂无描述'),'所属主线：'+(item.main_quest||'独立副本'),'推荐等级：'+(levelNames[item.level]||'待确认'),'推荐理由：'+(item.reason||'暂无理由')].join('\n');
   marker.addEventListener('mouseenter',()=>markerDetail(item));marker.addEventListener('focus',()=>markerDetail(item));
   marker.addEventListener('mouseleave',()=>{if(document.activeElement!==marker)detail.textContent=detailHint;});
   marker.addEventListener('blur',()=>{detail.textContent=detailHint;});
   scatter.append(marker);
  }
 }
 async function api(url,method='GET',data) { const r=await fetch(url,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined}); const value=await r.json();if(!r.ok){const error=Error(value.error||'请求失败，请稍后重试');error.code=value.code;throw error;}return value; }
 function render(data) {
  if(lastFailure&&data.batch_id&&data.batch_id!==failureBatchId)lastFailure='';
  lastBatchId=data.batch_id||null;
  list.replaceChildren();message.textContent=lastFailure||data.message;window.dispatchEvent(new CustomEvent('recommendations-view',{detail:data}));
  renderScatter(data.items||[]);
  for(const quadrant of ['投入区','降噪区','激活区','修复区','待确认']) {
   const section=document.createElement('section'),h=document.createElement('h3');h.textContent=quadrant;section.append(h);
   for(const item of data.items.filter(x=>quadrant==='待确认' ? x.stale||x.analysis_status==='pending'||!x.quadrants?.length : !x.stale&&x.analysis_status!=='pending'&&x.quadrants?.includes(quadrant))) {
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
 async function load(){if(refreshing)return;const version=++readVersion;try{const data=await api('/api/startup/recommendations');if(version===readVersion)render(data);}catch(e){if(version===readVersion){list.replaceChildren();renderScatter([]);message.textContent='推荐暂不可用，请稍后刷新';window.dispatchEvent(new CustomEvent('recommendations-view',{detail:{items:[],message:'推荐暂不可用，请稍后刷新'}}));}}}
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

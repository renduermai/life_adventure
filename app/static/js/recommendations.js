(() => {
 const list=document.querySelector('#recommend-list'), message=document.querySelector('#recommend-message'), button=document.querySelector('#recommend-refresh');
 async function api(url,method='GET',data) { const r=await fetch(url,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined}); const value=await r.json();if(!r.ok)throw Error(value.error||'请求失败，请稍后重试');return value; }
 function render(data) {
  list.replaceChildren();message.textContent=data.message;
  document.querySelectorAll('.quadrant .recommend-tags').forEach(x=>x.remove());
  ['投入区','降噪区','激活区','修复区'].forEach((q,index)=>{const tags=document.createElement('div');tags.className='recommend-tags';for(const item of data.items.filter(x=>!x.stale&&x.quadrants.includes(q))){const a=document.createElement('a');a.href=item.href;a.textContent=item.keyword;a.title=item.reason;tags.append(a);}document.querySelectorAll('.quadrant')[index].append(tags);});
  for(const quadrant of ['投入区','降噪区','激活区','修复区','待确认']) {
   const section=document.createElement('section'),h=document.createElement('h3');h.textContent=quadrant;section.append(h);
   for(const item of data.items.filter(x=>quadrant==='待确认' ? x.stale||!x.quadrants.length : !x.stale&&x.quadrants.includes(quadrant))) {
    const row=document.createElement('p'),link=document.createElement('a');link.textContent=item.keyword;link.href=item.href;link.className='task-title';row.append(link);
    const reason=document.createElement('span');reason.textContent=' · '+(item.stale?'已过期，请刷新':item.reason);row.append(reason);
    if(!item.stale) {const edit=document.createElement('button');edit.type='button';edit.className='button secondary';edit.textContent='修正象限';edit.addEventListener('click',async()=>{
     const selected=prompt('输入象限：投入区、降噪区、激活区或修复区',item.quadrants[0]||'投入区');if(selected===null)return;if(!['投入区','降噪区','激活区','修复区'].includes(selected)){message.textContent='请输入一个有效象限';return;}
     try{await api('/api/startup/task-analyses/'+item.analysis_id,'PATCH',{expected_version:item.analysis_version,keyword:item.keyword,quadrants:[selected]});message.textContent='已修正，请点击刷新任务结果';}catch(e){message.textContent=e.message;}
    });row.append(edit);}section.append(row);
   }list.append(section);
  }
 }
 let readVersion=0;
 async function load(){if(button.disabled)return;const version=++readVersion;try{const data=await api('/api/startup/recommendations');if(version===readVersion)render(data);}catch(e){if(version===readVersion){list.replaceChildren();document.querySelectorAll('.quadrant .recommend-tags').forEach(x=>x.remove());message.textContent='推荐暂不可用，请稍后刷新';}}}
 button.addEventListener('click',async()=>{++readVersion;button.disabled=true;message.textContent='正在分析，请稍候……';try{render(await api('/api/startup/refresh','POST',{request_id:crypto.randomUUID()}));window.dispatchEvent(new Event('recommendations-refreshed')); }catch(e){message.textContent=e.message+'；已保留上次结果';}finally{button.disabled=false;window.dispatchEvent(new Event('recommendations-refreshed'));}});
 window.addEventListener('state-saved',load);
 window.addEventListener('focus',load);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
 setInterval(()=>{if(!document.hidden)load();},30000);
 load();
})();

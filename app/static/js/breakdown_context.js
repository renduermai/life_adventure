(() => {
 const params = new URLSearchParams(location.search);
 if (!params.has('task_id') && !params.has('task_type')) return;
 const error = document.querySelector('#breakdown-error');
 const chat = document.querySelector('#chat');
 let version=0;
 async function load(focus=false) {
  const currentVersion=++version;
  try {
   const query = new URLSearchParams({task_type: params.get('task_type') || '',task_id: params.get('task_id') || ''});
   const response = await fetch('/api/startup/target?' + query);
   const data = await response.json();
   if(currentVersion!==version)return;
   if (!response.ok) throw Error(data.error || '目标无效或当前不可访问，请返回主线或副本列表。');
   document.querySelector('#breakdown-heading').textContent = '正在拆解：' + data.title;
   document.querySelector('#breakdown-description').textContent = data.description || '尚未填写描述';
   document.querySelector('#breakdown-progress').textContent = '所属主线：' + data.main_quest + ' · 进度：' + (data.progress === null ? '尚未配置' : data.progress + '%');
   const item = data.recommendation;
   document.querySelector('#breakdown-status').textContent = item?.stale ? '推荐已过期，请刷新' : item?.reason || '当前尚未评估';
   const steps = document.querySelector('#breakdown-steps'); steps.replaceChildren();
   for (const title of data.steps) { const li = document.createElement('li'); li.textContent = title; steps.append(li); }
   const back = document.querySelector('#breakdown-return'); back.href = data.href;
   error.textContent='';document.querySelector('#breakdown-context').hidden = false;
   if(focus){chat.focus(); chat.scrollIntoView({behavior:'smooth'});}
  } catch(e) { if(currentVersion!==version)return;document.querySelector('#breakdown-context').hidden=true;error.textContent = e.message;if(focus)chat.focus(); }
 }
 window.addEventListener('state-saved',()=>load());
 window.addEventListener('recommendations-refreshed',()=>load());
 window.addEventListener('focus',()=>load());
 setInterval(()=>{if(!document.hidden)load();},30000);
 load(true);
})();

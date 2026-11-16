(() => {
 const pressure=document.querySelector('#pressure'),energy=document.querySelector('#energy');
 const message=document.querySelector('#state-message'),retry=document.querySelector('#state-retry');
 const state=window.startupState={confirmed:false,snapshotId:null};
 let generation=0,difficulty='',ready=false,saving=false,revision=0,savedRevision=0,timer,pending=null;
 const names=['投入区','降噪区','激活区','修复区'];
 const hints=['适合直接投入行动','先理清重点，再做一件事','从轻松、有趣的事情开始','允许减负、休息和非常小的动作'];
 async function api(url,method='GET',data){
  const response=await fetch(url,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});
  const value=await response.json();if(!response.ok){const error=Error(value.error||'状态保存失败，请重试');error.status=response.status;throw error;}return value;
 }
 function preview(){
  const p=Number(pressure.value),e=Number(energy.value),index=e>=50?(p<50?0:1):(p<50?2:3);
  state.pressure=p;state.energy=e;state.quadrant=names[index];state.difficulty=difficulty;
  document.querySelector('#pressure-output').textContent=p;document.querySelector('#energy-output').textContent=e;
  const dot=document.querySelector('#state-dot');dot.setAttribute('cx',p);dot.setAttribute('cy',100-e);
  document.querySelectorAll('.quadrant').forEach((node,i)=>{node.classList.toggle('is-current',i===index);node.setAttribute('aria-current',i===index?'true':'false');});
  document.querySelector('#state-summary').textContent=`${names[index]} · ${hints[index]}`;
  window.dispatchEvent(new Event('state-readiness'));
 }
 async function load(){
  const data=await api('/api/startup/current');generation=data.generation;difficulty=data.difficulty||'';ready=true;
  state.snapshotId=data.snapshot_id||null;
  if(revision===savedRevision&&data.snapshot_id){pressure.value=data.pressure;energy.value=data.energy;state.confirmed=true;}
  preview();return data;
 }
 async function save(){
  clearTimeout(timer);if(saving||revision===savedRevision)return;
  saving=true;retry.hidden=true;message.textContent='正在保存……';
  try{
   if(!ready)await load();
   const target=revision;
   // Retry uncertain results with the same idempotency key; serialize all writes.
   pending=pending||{target,data:{pressure:Number(pressure.value),energy:Number(energy.value),difficulty,confirmed:true,expected_generation:generation,request_id:crypto.randomUUID()}};
   const attempt=pending,data=await api('/api/startup/states','POST',attempt.data);
   generation=data.generation;state.snapshotId=data.snapshot_id;savedRevision=attempt.target;pending=null;
   state.confirmed=revision===savedRevision;message.textContent=state.confirmed?'已自动保存':'正在保存最新数值……';
   window.dispatchEvent(new Event('state-saved'));window.dispatchEvent(new Event('state-readiness'));
  }catch(error){
   message.textContent=error.message+'；当前滑杆数值已保留。';retry.hidden=false;
   if(error.status===409){pending=null;ready=false;}
  }finally{saving=false;if(retry.hidden&&revision!==savedRevision)save();}
 }
 function changed(){revision++;state.confirmed=false;preview();message.textContent='停拖后自动保存';retry.hidden=true;clearTimeout(timer);timer=setTimeout(save,450);}
 for(const slider of [pressure,energy]){slider.addEventListener('input',changed);slider.addEventListener('change',save);}
 retry.addEventListener('click',save);
 document.addEventListener('visibilitychange',()=>{if(document.hidden&&revision!==savedRevision)save();});
 window.addEventListener('beforeunload',event=>{if(revision!==savedRevision){event.preventDefault();event.returnValue='';}});
 pressure.disabled=true;energy.disabled=true;
 preview();load().then(()=>{message.textContent='拖动滑杆即可调整，停拖后自动保存。';}).catch(error=>{message.textContent=error.message;}).finally(()=>{pressure.disabled=false;energy.disabled=false;});
})();

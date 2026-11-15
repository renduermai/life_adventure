(() => {
  const pressure=document.querySelector('#pressure'), energy=document.querySelector('#energy'), difficulty=document.querySelector('#difficulty');
  const summary=document.querySelector('#state-summary'), message=document.querySelector('#state-message'), form=document.querySelector('#state-form');
  let generation=0, ready=false, pending=null, source=null, sourcePlan=null, saving=false, readVersion=0;
  const state=window.startupState={confirmed:false,snapshotId:null};
  function announce() { window.dispatchEvent(new Event('state-readiness')); }
  function preview() {
    const p=Number(pressure.value), e=Number(energy.value);
    document.querySelector('#pressure-output').textContent=p;document.querySelector('#energy-output').textContent=e;
    const dot=document.querySelector('#state-dot');dot.setAttribute('cx',Math.max(2.5,Math.min(97.5,p)));dot.setAttribute('cy',Math.max(2.5,Math.min(97.5,100-e)));
    const name=e>=50?(p<50?'投入区':'降噪区'):(p<50?'激活区':'修复区');
    summary.textContent=`当前预览：${name} · 压力 ${p} · 能量 ${e}（请确认后保存）`;
  }
  function changed() { ++readVersion;state.confirmed=false;pending=null;preview();announce(); }
  [pressure,energy,difficulty].forEach(x=>x.addEventListener('input',changed));
  async function load(replace=true) {
    if(!replace&&!ready)replace=true;
    const version=++readVersion;
    try {
      const response=await fetch('/api/startup/current');const data=await response.json();
      if(!response.ok)throw Error(data.error||'读取失败');
      if(version!==readVersion||saving)return;
      ready=true;
      if(!replace) {
        if((data.snapshot_id||null)!==state.snapshotId) { state.confirmed=false;announce();message.textContent='当前状态已在其他页面改变，请读取已保存状态或重新确认。'; }
        generation=data.generation;return;
      }
      generation=data.generation;source=null;sourcePlan=null;pending=null;
      state.snapshotId=data.snapshot_id||null;state.confirmed=Boolean(state.snapshotId);
      if(state.confirmed) { pressure.value=data.pressure;energy.value=data.energy;difficulty.value=data.difficulty; }
      preview();if(state.confirmed)summary.textContent=`已保存：${data.quadrant} · 压力 ${data.pressure} · 能量 ${data.energy}`;
      message.textContent=state.confirmed?'已确认，可以刷新象限。':'先描述感受或拖动滑杆，再确认状态。';announce();
    } catch(error) { if(version===readVersion){ready=false;state.confirmed=false;message.textContent=error.message;announce();} }
  }
  window.addEventListener('state-advice',event=>{
    if(saving)return;
    const advice=event.detail;
    pressure.value=advice.response.pressure;energy.value=advice.response.energy;difficulty.value=advice.response.difficulty;
    source=advice.plan_id?null:advice.id;sourcePlan=advice.plan_id||null;generation=advice.base_generation;changed();
    message.textContent='已载入 AI 建议值。可拖动滑杆修改，再点击确认并保存。';
    form.scrollIntoView({behavior:'smooth',block:'center'});pressure.focus({preventScroll:true});
  });
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(saving)return;
    if(!ready){message.textContent='请先登录并读取已保存状态。';return;}
    saving=true;++readVersion;state.confirmed=false;announce();
    form.querySelectorAll('input,textarea,button').forEach(x=>x.disabled=true);
    pending=pending||{pressure:Number(pressure.value),energy:Number(energy.value),difficulty:difficulty.value,confirmed:true,source_turn_id:source,source_plan_id:sourcePlan,request_id:crypto.randomUUID(),expected_generation:generation};
    try {
      const response=await fetch('/api/startup/states',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pending)});const data=await response.json();
      if(!response.ok){if(response.status===409)pending=null;throw Error(data.error||'保存失败');}
      generation=data.generation;pending=null;source=null;sourcePlan=null;state.snapshotId=data.snapshot_id;state.confirmed=true;
      summary.textContent=`已保存：${data.quadrant} · 压力 ${data.pressure} · 能量 ${data.energy}`;message.textContent='已确认，现在可以刷新象限与推荐。';
      window.dispatchEvent(new Event('state-saved'));
    } catch(error){message.textContent=error.message;}
    finally{saving=false;form.querySelectorAll('input,textarea,button').forEach(x=>x.disabled=false);announce();}
  });
  document.querySelector('#state-manual').addEventListener('click',async()=>{await load(false);window.dispatchEvent(new Event('manual-state'));});
  document.querySelector('#state-reload').addEventListener('click',()=>load());
  window.addEventListener('recommendations-refreshed',()=>load(false));
  window.addEventListener('focus',()=>{if(!saving)load(false);});
  window.addEventListener('manual-state',()=>{source=null;sourcePlan=null;changed();message.textContent='已切换到手动输入，请确认当前数值。';});
  load();
})();

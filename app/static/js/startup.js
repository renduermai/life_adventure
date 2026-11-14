(() => {
  const pressure=document.querySelector('#pressure'), energy=document.querySelector('#energy'), difficulty=document.querySelector('#difficulty');
  const summary=document.querySelector('#state-summary'), message=document.querySelector('#state-message'), form=document.querySelector('#state-form');
  let generation=0, ready=false, pending=null;
  function update() {
    const p=Number(pressure.value), e=Number(energy.value);
    document.querySelector('#pressure-output').textContent=p; document.querySelector('#energy-output').textContent=e;
    const dot=document.querySelector('#state-dot'); dot.setAttribute('cx',Math.max(2.5,Math.min(97.5,p))); dot.setAttribute('cy',Math.max(2.5,Math.min(97.5,100-e)));
    const name=e>=50 ? (p<50?'投入区':'降噪区') : (p<50?'激活区':'修复区');
    summary.textContent=`当前预览：${name} · 压力 ${p} · 能量 ${e}（尚未保存的调整）`;
    pending=null;
  }
  pressure.addEventListener('input',update); energy.addEventListener('input',update); difficulty.addEventListener('input',update);
  async function load() {
    try {
      const response=await fetch('/api/startup/current'); const data=await response.json();
      if (!response.ok) throw new Error(data.error || '读取失败');
      generation=data.generation; ready=true;
      if (data.state!==null && data.pressure!==undefined) { pressure.value=data.pressure; energy.value=data.energy; difficulty.value=data.difficulty; update(); summary.textContent=`已保存：${data.quadrant} · 压力 ${data.pressure} · 能量 ${data.energy}`; }
      else update();
    } catch(error) { message.textContent=error.message; update(); }
  }
  form.addEventListener('submit',async event => {
    event.preventDefault(); if (!ready) { message.textContent='请先登录并确保数据库可用，然后刷新页面。'; return; }
    const button=form.querySelector('button'); button.disabled=true;
    const data=pending || {pressure:Number(pressure.value),energy:Number(energy.value),difficulty:difficulty.value,confirmed:true,request_id:crypto.randomUUID(),expected_generation:generation}; pending=data;
    try {
      const response=await fetch('/api/startup/states',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}); const result=await response.json();
      if (!response.ok) { if (response.status===409) pending=null; throw new Error(result.error || '保存失败'); }
      generation=result.generation; pending=null; summary.textContent=`已保存：${result.quadrant} · 压力 ${result.pressure} · 能量 ${result.energy}`; message.textContent='状态已保存。';
    } catch(error) { message.textContent=error.message; }
    finally { button.disabled=false; }
  });
  load();
})();

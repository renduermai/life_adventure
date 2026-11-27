(() => {
 const chart=document.querySelector('.state-chart'),scatter=document.querySelector('#task-scatter');
 const detail=document.querySelector('#item-scatter-detail'),tooltip=document.querySelector('#item-scatter-tooltip');
 const button=document.querySelector('#items-analyze'),message=document.querySelector('#items-analysis-message');
 const quadrants=['投入区','降噪区','激活区','修复区'];
 let items=[],busy=false,reading=0,lastReport='',resizeTimer;
 const uncertain=new Map();
 async function api(url,method='GET',data){
  const response=await fetch(url,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});
  const value=await response.json();if(!response.ok){const error=Error(value.error||'事项分析暂不可用');error.status=response.status;throw error;}return value;
 }
 function hash(value){let result=2166136261;for(const char of value)result=Math.imul(result^char.charCodeAt(0),16777619);return result>>>0;}
 function info(item){
  const result=item.analysis.result;
  return [item.description,`重要程度 ${item.importance} · 紧急程度 ${item.urgency}`,'当前进展：'+(item.progress||'尚未填写'),'适配原因：'+result.reason,'启动动作：'+result.action].join('\n');
 }
 function highlight(){
  for(const marker of scatter.children)marker.classList.toggle('matches-state',marker.dataset.quadrant===window.startupState?.quadrant);
 }
 function show(item,marker){
  const text=info(item);tooltip.textContent=text;detail.textContent=text;tooltip.hidden=false;
  const rect=marker.getBoundingClientRect(),width=Math.min(320,innerWidth-24);
  tooltip.style.width=width+'px';tooltip.style.left=Math.max(12,Math.min(innerWidth-width-12,rect.left))+'px';
  tooltip.style.top=Math.max(12,Math.min(innerHeight-tooltip.offsetHeight-12,rect.bottom+8))+'px';
 }
 function render(){
  tooltip.hidden=true;scatter.replaceChildren();
  const groups=quadrants.map(q=>items.filter(x=>x.analysis?.result?.quadrant===q));
  const columns=Math.max(2,Math.floor((chart.clientWidth/2-28)/32));
  const rows=Math.max(1,...groups.map(group=>Math.ceil(group.length/columns)));
  // Grow the chart for dense groups: every item keeps its own non-overlapping point.
  chart.style.aspectRatio='auto';
  chart.style.height=Math.max(chart.clientWidth/(innerWidth<=1000?1:1.25),2*(100+rows*34))+'px';
  const chartHeight=chart.clientHeight;
  const stateDot=document.querySelector('#state-dot');
  stateDot.setAttribute('rx',14/chart.clientWidth*100);stateDot.setAttribute('ry',14/chartHeight*100);
  groups.forEach((group,index)=>{
   const used=new Set(),capacity=columns*rows;
   for(const item of group.sort((a,b)=>a.id.localeCompare(b.id))){
    let slot=hash(item.id)%capacity;while(used.has(slot))slot=(slot+1)%capacity;used.add(slot);
    const x=(index%2?50:0)+5+(slot%columns+.5)*40/columns;
    const y=(index<2?0:50)+(index<2?90:35)/chartHeight*100+Math.floor(slot/columns)*34/chartHeight*100;
    const marker=document.createElement('button');marker.type='button';marker.className='item-marker';
    marker.style.left=x+'%';marker.style.top=y+'%';marker.dataset.quadrant=quadrants[index];marker.dataset.itemId=item.id;
    marker.setAttribute('aria-label',(item.analysis.result.keyword||item.description)+' · '+quadrants[index]+'，点击查看或编辑');
    marker.title=info(item);
    marker.addEventListener('mouseenter',()=>show(item,marker));marker.addEventListener('focus',()=>show(item,marker));
    marker.addEventListener('mouseleave',()=>{tooltip.hidden=true;});marker.addEventListener('blur',()=>{tooltip.hidden=true;});
    marker.addEventListener('click',()=>{show(item,marker);window.dispatchEvent(new CustomEvent('item-open',{detail:item.id}));});
    scatter.append(marker);
   }
  });
  highlight();
  const count=groups.reduce((sum,group)=>sum+group.length,0);
  message.textContent=lastReport||(!items.length?'先新增并保存事情，再开始分析。':`已分类 ${count} 件，待分析或待确认 ${items.length-count} 件。`);
  if(!count)detail.textContent=items.length?'事项尚无有效分类，请开始分析；待确认事项不会强行绘点。':'先记录此刻想到的事情，再分析适配象限。';
 }
 async function load(){
  const seq=++reading;let all=[],offset=0;
  try{
   do{const data=await api('/api/startup/items?offset='+offset);if(seq!==reading)return;all.push(...data.items);offset=data.next_offset;}while(offset!==null);
   items=[...new Map(all.map(item=>[item.id,item])).values()];render();return true;
  }catch(error){if(seq===reading){scatter.replaceChildren();tooltip.hidden=true;message.textContent=error.message+'；可重新点击开始分析读取。';}return false;}
 }
 async function analyze(target=null){
  if(busy)return;busy=true;button.disabled=true;lastReport='';
  let success=0,cached=0,failed=0,pending=0;
  try{
   if(!await load())return;
   const candidates=target?items.filter(item=>item.id===target):items;
   if(!candidates.length){message.textContent=target?'这件事项已不可用，请重新读取。':'没有可分析的事项，请先新增并保存。';return;}
   for(const [index,item] of candidates.entries()){
    message.textContent=`正在分析 ${index+1}/${candidates.length}，已保存的成功结果会保留……`;
    const requestId=uncertain.get(item.id)||crypto.randomUUID();uncertain.set(item.id,requestId);
    try{
     const data=await api('/api/startup/items/'+item.id+'/analyze','POST',{request_id:requestId});uncertain.delete(item.id);
     items=items.map(old=>old.id===item.id?data.item:old);
     if(data.cached)cached++;
     if(data.item.analysis?.error){failed++;}
     else if(data.item.analysis?.result?.quadrant)success++;
     else pending++;
     render();window.dispatchEvent(new Event('item-analysis-updated'));
    }catch(error){
     failed++;if(error.status&&error.status<500)uncertain.delete(item.id);
     lastReport='部分事项未完成：'+error.message+'；已保存结果保留。';
    }
   }
   lastReport=`本次：已分类 ${success} 件，待确认或处理中 ${pending} 件，失败 ${failed} 件；复用 ${cached} 件缓存。`+(failed?' 失败项可在列表单独重试。':'');
   await load();window.dispatchEvent(new Event('item-analysis-updated'));
  }finally{busy=false;button.disabled=false;}
 }
 button.addEventListener('click',()=>analyze());
 window.addEventListener('item-analyze',event=>analyze(event.detail));
 window.addEventListener('items-changed',()=>{lastReport='';load();});
 window.addEventListener('state-readiness',highlight);
 window.addEventListener('focus',()=>{if(!busy)load();});
 window.addEventListener('scroll',()=>{tooltip.hidden=true;},true);
 window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(render,100);});
 load();
})();

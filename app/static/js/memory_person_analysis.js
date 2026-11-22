(() => {
 const make=(tag,text='')=>{const e=document.createElement(tag);e.textContent=text;return e;};
 const button=(text,fn)=>{const b=make('button',text);b.type='button';b.className='button secondary';b.onclick=fn;return b;};
 async function api(path,method='GET',data){const r=await fetch('/api/shining-memories/'+path,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});const result=await r.json();if(!r.ok)throw Error(result.error||'请求未完成，旧结果保留。');return result;}
 window.addEventListener('memory-person-selected',event=>{
  const p=event.detail.person,panel=document.querySelector('#person-analysis');if(!panel)return;
  panel.replaceChildren(make('h3','人物分析'));const result=make('div'),message=make('p');message.setAttribute('role','status');panel.append(result,message);
  const controls=make('div'),scope={include_tasks:false,include_notes:false,task_ids:[],quest_ids:[],note_ids:[]};let preview=null,busy=false;
  const previewArea=make('div'),consentLabel=make('label'),consent=make('input');consent.type='checkbox';consentLabel.append(consent,document.createTextNode(' 我已核对预览，允许将这些内容发送到上述外部模型。'));
  const confirm=button('确认并分析',analyze);confirm.disabled=true;consent.onchange=()=>confirm.disabled=!consent.checked||!preview||busy;
  function invalidate(){preview=null;previewArea.replaceChildren();consent.checked=false;confirm.disabled=true;}
  function display(data){result.replaceChildren();const rec=data.recommendation;
   if(data.last_attempt?.state==='failed')result.append(make('p','最近分析失败：'+(data.last_attempt.error_code||'未知错误')+'。旧分析保留。'));
   if(!data.analysis){result.append(make('p',rec.reason||'尚未分析'));return;}
   const a=data.analysis;result.append(make('h4',a.meaning_label),make('p',a.meaning_summary));
   if(data.stale)result.append(make('p','旧分析已过期，请重新预览后分析。'));
   result.append(make('strong',rec.score===null?rec.reason:'推荐联系指数：'+rec.score+'%'),make('p','仅用于主观辅助排序，不代表关系成功概率。'));
   for(const text of a.positive_factors)result.append(make('p','正面经历：'+text));
   if(a.negative.reason)result.append(make('p','负面影响 / 边界：'+a.negative.reason));
   if(rec.components)result.append(make('p',Object.entries(rec.components).map(([k,v])=>k+' '+v).join(' · ')));
   result.append(make('p','联系建议：'+(a.contact_suggestion||'暂无建议')));
   const evidence=make('details');evidence.append(make('summary','查看判断依据'));
   for(const [key,label] of [['meaning','人物意义'],['topic','交流话题'],['goal','目标关联'],['negative','负面影响']]){const j=a[key];evidence.append(make('p',label+'：'+j.reason));for(const e of j.evidence)evidence.append(make('blockquote',e.quote));}result.append(evidence);
   for(const related of a.related){const row=make('div');row.append(make('p','可能相关：'+related.reason));const link=make('a',related.kind==='note'?'查看相关杂念':'查看相关任务');link.href=related.href;row.append(link,button('忽略这条建议',()=>row.remove()));result.append(row);}
  }
  function chooser(kind,label,parent){const search=make('input');search.type='search';search.maxLength=80;search.placeholder='按关键词查找'+label;const rows=make('div'),more=button('更多候选',()=>load(true));more.hidden=true;let next=null,reading=0;
   async function load(append=false){const token=++reading;try{const data=await api('people-sources?'+new URLSearchParams({kind,q:search.value,offset:append?next:0}));if(!panel.isConnected||token!==reading)return;if(!append)rows.replaceChildren();next=data.next_offset;more.hidden=next===null;for(const item of data.items){const key={quest:'quest_ids',task:'task_ids',note:'note_ids'}[kind],box=make('input');box.type='checkbox';box.checked=scope[key].includes(item.id);box.onchange=()=>{const current=scope[key];if(box.checked&&current.length>=5){box.checked=false;message.textContent='每类最多选择5条。';return;}scope[key]=box.checked?[...current,item.id]:current.filter(id=>id!==item.id);invalidate();};const line=make('label');line.className='memory-source';line.append(box,document.createTextNode(item.title),make('small',item.summary));rows.append(line);}if(!data.items.length&&!append)rows.append(make('p','暂无符合条件的候选。'));}catch(error){message.textContent=error.message;}}
   parent.append(make('p',label),search,button('查找候选',()=>load()),rows,more);
  }
  for(const [key,label,kinds] of [['include_tasks','允许参考主线、副本',[['quest','主线'],['task','副本']]],['include_notes','允许参考杂念',[['note','杂念']]]]){const box=make('input');box.type='checkbox';const line=make('label');line.append(box,document.createTextNode(' '+label));const region=make('div');region.hidden=true;for(const [kind,name] of kinds)chooser(kind,name,region);box.onchange=()=>{scope[key]=box.checked;region.hidden=!box.checked;if(!box.checked){if(key==='include_tasks'){scope.task_ids=[];scope.quest_ids=[];}else scope.note_ids=[];region.querySelectorAll('input[type=checkbox]').forEach(e=>e.checked=false);}invalidate();};controls.append(line,region);}
  const previewButton=button('预览发送范围',async()=>{if(busy)return;invalidate();message.textContent='正在准备预览…';try{const data=await api('people/'+p.id+'/preview','POST',scope);if(!panel.isConnected)return;preview=data;previewArea.append(make('p',data.notice),make('strong','模型：'+data.provider.name+' / '+data.provider.model));for(const [key,value] of Object.entries(data.payload.sources)){if(!value)continue;const label=key.startsWith('person:')?'人物记录':key.startsWith('event:')?'历史事件':key.startsWith('quest:')?'主线':key.startsWith('task:')?'副本':'杂念';const d=make('details');d.append(make('summary',label),make('p',value));previewArea.append(d);}if(data.payload.more_events_omitted)previewArea.append(make('p','本次仅发送最近10条事件，较早事件未发送。'));message.textContent='请核对范围，再勾选确认。';}catch(error){message.textContent=error.message;}});
  async function analyze(){if(busy||!preview||!consent.checked)return;busy=true;confirm.disabled=true;previewButton.disabled=true;controls.querySelectorAll('input,button').forEach(e=>e.disabled=true);message.textContent='正在分析，请稍候…';try{const data=await api('people/'+p.id+'/analysis','POST',{...scope,preview_token:preview.preview_token,consent_external:true,request_id:crypto.randomUUID()});if(!panel.isConnected)return;display(data);message.textContent=data.cached?'已复用保存的分析，无新增调用。':'分析已保存。';window.dispatchEvent(new Event('memory-analysis-updated'));}catch(error){if(panel.isConnected){message.textContent=error.message;try{display(await api('people/'+p.id+'/analysis'));}catch{}}}finally{busy=false;confirm.disabled=!consent.checked||!preview;previewButton.disabled=false;controls.querySelectorAll('input,button').forEach(e=>e.disabled=false);}}
  panel.append(make('p','人物描述会发送至外部模型；任务与杂念默认不发送。'),controls,previewButton,previewArea,consentLabel,confirm);
  api('people/'+p.id+'/analysis').then(data=>{if(panel.isConnected)display(data);}).catch(error=>{if(panel.isConnected)message.textContent=error.message;});
 });
})();

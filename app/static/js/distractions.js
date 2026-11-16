(() => {
 const root=document.querySelector('#thoughts'), list=document.querySelector('#thought-list'), detail=document.querySelector('#thought-detail');
 const form=document.querySelector('#thought-form'), input=document.querySelector('#thought-input'), send=document.querySelector('#thought-send');
 const message=document.querySelector('#thought-message'), more=document.querySelector('#thought-more'), reload=document.querySelector('#thought-reload');
 let items=[], next=null, selected=null, busy=false, pending=null, readSeq=0;
 const endpoint='/api/distractions/notes';
 const make=(tag,text,cls)=>{const e=document.createElement(tag); e.textContent=text; if(cls)e.className=cls; return e;};
 function timestamp(value){try{return new Intl.DateTimeFormat('zh-CN',{timeZone:root.dataset.timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));}catch{return value;}}
 async function api(url,method='GET',body){
  let response; try{response=await fetch(url,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});}catch{const e=Error('网络连接失败，请重试；输入已保留。');e.uncertain=true;throw e;}
  let data;try{data=await response.json();}catch{const e=Error('服务器响应异常，请重试；输入已保留。');e.uncertain=true;throw e;}
  if(!response.ok){const e=Error(response.status===401?'请先登录账号，再记录杂念。':data.error||'操作失败，请重试。');e.status=response.status; e.uncertain=response.status>=500;throw e;}return data;
 }
 function controls(){send.disabled=busy;input.disabled=busy;more.disabled=busy;reload.disabled=busy;list.querySelectorAll('button').forEach(b=>b.disabled=busy);}
 function showDetail(){detail.replaceChildren();const item=items.find(x=>x.id===selected);if(!item){detail.append(make('p','选择一条杂念，在这里回看。','muted'));return;}detail.append(make('time',timestamp(item.created_at),'muted'),make('p',item.content,'thought-full'));}
 function render(){list.replaceChildren();if(!items.length)list.append(make('p','这里还没有记录。写下第一个念头吧。','muted'));
  for(const item of items){const row=make('article','','thought-item'), choose=make('button','','thought-select');choose.type='button';choose.setAttribute('aria-pressed',String(selected===item.id));choose.append(make('span',item.content,'thought-preview'),make('time',timestamp(item.created_at),'thought-date'));choose.addEventListener('click',()=>{selected=item.id;render();});
   const remove=make('button','删除','button secondary thought-delete');remove.type='button';remove.setAttribute('aria-label','删除这条杂念');remove.addEventListener('click',()=>destroy(item));row.append(choose,remove);list.append(row);}
  more.hidden=next===null;showDetail();controls();
 }
 async function load(append=false){const seq=++readSeq;reload.hidden=true;try{const data=await api(endpoint+'?offset='+(append?next:0));if(seq!==readSeq)return;items=append?[...new Map([...items,...data.items].map(x=>[x.id,x])).values()]:data.items;next=data.next_offset;render();}catch(e){if(seq===readSeq){message.textContent=e.message;reload.hidden=false;}}}
 async function destroy(item){if(busy||!confirm('确定删除这条杂念？删除后不会显示在列表中。'))return;busy=true;++readSeq;controls();try{await api(endpoint+'/'+item.id,'DELETE',{expected_version:item.version});if(selected===item.id)selected=null;message.textContent='已删除这条记录。';await load();}catch(e){message.textContent=e.message;reload.hidden=false;}finally{busy=false;controls();}}
 form.addEventListener('submit',async event=>{event.preventDefault();if(busy)return;const content=input.value;if(!content.trim()){message.textContent='先写下一点内容吧。';input.focus();return;}
  if(!pending||pending.content!==content)pending={request_id:crypto.randomUUID(),content};busy=true;++readSeq;controls();message.textContent='正在保存…';
  try{const saved=await api(endpoint,'POST',pending);pending=null;input.value='';selected=saved.id;message.textContent='已保存。';await load();}
  catch(e){message.textContent=e.message;if(!e.uncertain)pending=null;}finally{busy=false;controls();}
 });
 more.addEventListener('click',()=>{if(!busy&&next!==null)load(true);});reload.addEventListener('click',()=>load());load();
})();

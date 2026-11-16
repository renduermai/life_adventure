(() => {
 const form=document.querySelector('#item-form'),list=document.querySelector('#items-list'),message=document.querySelector('#items-message');
 const fields=Object.fromEntries(['description','importance','urgency','progress'].map(key=>[key,document.querySelector('#item-'+key)]));
 const formMessage=document.querySelector('#item-form-message'),more=document.querySelector('#items-more'),reload=document.querySelector('#items-reload');
 const newButton=document.querySelector('#item-new');
 let items=[],nextOffset=null,editing=null,busy=false,pending=null,reading=0;
 async function api(url,method='GET',data){
  const response=await fetch(url,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});
  const value=await response.json();if(!response.ok){const error=Error(value.error||'事项暂不可用，请重试');error.status=response.status;throw error;}return value;
 }
 function node(tag,text,cls){const el=document.createElement(tag);el.textContent=text;if(cls)el.className=cls;return el;}
 function controls(){
  form.querySelectorAll('input,textarea,button').forEach(el=>el.disabled=busy);
  list.querySelectorAll('button').forEach(el=>el.disabled=busy);
  newButton.disabled=busy;more.disabled=busy;reload.disabled=busy;
 }
 function values(){return {description:fields.description.value,importance:Number(fields.importance.value),urgency:Number(fields.urgency.value),progress:fields.progress.value};}
 function outputs(){for(const key of ['importance','urgency'])document.querySelector('#item-'+key+'-output').textContent=fields[key].value;}
 for(const key of ['importance','urgency'])fields[key].addEventListener('input',outputs);
 function open(item=null){
  if(busy)return;
  if(!form.hidden&&!confirm('放弃当前未保存的输入？'))return;
  editing=item;pending=null;form.reset();formMessage.textContent='';
  if(item)for(const key of Object.keys(fields))fields[key].value=item[key];
  outputs();document.querySelector('#item-form-heading').textContent=item?'编辑事情':'新增事情';form.hidden=false;fields.description.focus();
 }
 function render(){
  list.replaceChildren();
  if(!items.length)list.append(node('p','还没有记录事情，想到什么就先记下来。','muted'));
  for(const item of items){
   const card=node('article','','startup-item');card.dataset.itemId=item.id;
   card.append(node('h3',item.description),node('p',`重要程度 ${item.importance} · 紧急程度 ${item.urgency}`,'muted'));
   const progress=node('p',item.progress?'当前进展：'+item.progress:'当前进展：尚未填写','item-progress-preview');progress.title=item.progress;card.append(progress);
   const edit=node('button','编辑','button secondary');edit.type='button';edit.addEventListener('click',()=>open(item));
   const remove=node('button','删除','button secondary');remove.type='button';remove.addEventListener('click',()=>destroy(item));card.append(edit,remove);list.append(card);
  }
  more.hidden=nextOffset===null;controls();
 }
 async function load(append=false){
  const seq=++reading;reload.hidden=true;
  try{
   const data=await api('/api/startup/items?offset='+(append?nextOffset||0:0));if(seq!==reading)return;
   items=append?[...new Map([...items,...data.items].map(x=>[x.id,x])).values()]:data.items;nextOffset=data.next_offset;render();
  }catch(error){if(seq===reading){message.textContent=error.message;reload.hidden=false;}}
 }
 async function destroy(item){
  if(busy||!confirm('删除这件事情？删除后将从当前列表移除。'))return;
  busy=true;++reading;controls();
  try{await api('/api/startup/items/'+item.id,'DELETE',{expected_version:item.version});
   if(editing?.id===item.id){form.hidden=true;editing=null;pending=null;}
   message.textContent='已删除事情。';await load();
  }catch(error){message.textContent=error.message;reload.hidden=false;}
  finally{busy=false;controls();}
 }
 newButton.addEventListener('click',()=>open());
 document.querySelector('#item-cancel').addEventListener('click',()=>{form.hidden=true;editing=null;pending=null;});
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;
  if(!fields.description.value.trim()){formMessage.textContent='请填写事件描述。';return;}
  busy=true;++reading;controls();formMessage.textContent='正在保存……';
  const data=values();
  try{
   if(editing)data.expected_version=editing.version;
   else{const signature=JSON.stringify(data);if(!pending||pending.signature!==signature)pending={signature,id:crypto.randomUUID()};data.request_id=pending.id;}
   await api('/api/startup/items'+(editing?'/'+editing.id:''),editing?'PATCH':'POST',data);
   form.hidden=true;form.reset();editing=null;pending=null;formMessage.textContent='';message.textContent='已保存事情，可以继续新增。';await load();
  }catch(error){formMessage.textContent=error.message+'；输入已保留。'+(error.status===409?' 请先复制需要保留的内容，取消编辑并重新读取事项，再重新编辑。':'');if(error.status===409)reload.hidden=false;}
  finally{busy=false;controls();}
 });
 more.addEventListener('click',()=>load(true));reload.addEventListener('click',()=>load());
 window.addEventListener('beforeunload',event=>{if(!form.hidden&&(fields.description.value||fields.progress.value)){event.preventDefault();event.returnValue='';}});
 load();
})();

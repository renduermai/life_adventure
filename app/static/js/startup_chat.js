(() => {
 const form=document.querySelector('#chat-form'),input=document.querySelector('#chat-input'),list=document.querySelector('#chat-messages'),status=document.querySelector('#chat-status');
 const newButton=document.querySelector('#chat-new'),freeButton=document.querySelector('#chat-free'),include=document.querySelector('#chat-include-tasks');
 const key='adventure-assistant-v3';let owner=null,target=null,turns=[],pending=null,busy=false,ready=false,storageAvailable=true;
 async function api(url,method='GET',data){const response=await fetch(url,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});const value=await response.json();if(!response.ok){const error=Error(value.error||'对话暂不可用，请稍后重试');error.code=value.code;error.status=response.status;throw error;}return value;}
 function el(tag,text,cls){const node=document.createElement(tag);node.textContent=text;if(cls)node.className=cls;return node;}
 function save(){try{sessionStorage.setItem(key,JSON.stringify({owner_id:owner,target,turns:turns.slice(-12),pending,include_tasks:include.checked}));}catch(_){storageAvailable=false;status.textContent='标签页存储不可用，对话暂存于当前页面，刷新将清空。';}}
 function clear(){try{sessionStorage.removeItem(key);}catch(_){}turns=[];pending=null;list.replaceChildren();}
 function controls(){input.disabled=busy||!ready;form.querySelector('button').disabled=busy||!ready;include.disabled=busy;newButton.disabled=busy||!owner;freeButton.disabled=busy||!owner;}
 function mode(){document.querySelector('#chat-mode').textContent=target?'主副本拆解':'自由对话';freeButton.hidden=!target;const box=document.querySelector('#chat-target');box.replaceChildren();box.hidden=!target;if(target){box.append(el('strong','正在拆解：'+target.title),el('p',target.description||'尚无任务描述'));const link=el('a','返回原任务');link.href=target.href;box.append(link);}}
 function formatted(reply){let text=reply.reply;for(const [name,label] of [['understanding','任务理解'],['completed','目前已完成'],['today_goal','本次目标']])if(reply[name])text+='\n'+label+'：'+reply[name];if(reply.steps?.length)text+='\n'+reply.steps.map((step,i)=>`${i+1}. ${step.title}\n${step.detail}\n完成标志：${step.done_when}（约${step.minutes}分钟，估计）`).join('\n');if(reply.minimum_action)text+='\n最小启动动作：'+reply.minimum_action;return text;}
 function render(){list.replaceChildren();for(const turn of turns){const row=el('article','','chat-turn');row.append(el('p','你：'+turn.message,'chat-user'),el('p',turn.reply,'chat-answer'));if(turn.response?.steps?.length){const copy=el('button','复制步骤','button secondary');copy.type='button';copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(turn.response.steps.map((s,i)=>`${i+1}. ${s.title}\n${s.detail}\n完成标志：${s.done_when}`).join('\n\n'));status.textContent='步骤已复制，可在左侧手动新增事情。';}catch(_){status.textContent='复制不可用，可直接选中回复文字复制。';}});row.append(copy);}list.append(row);}if(turns.length)list.scrollTop=list.scrollHeight;}
 function history(){const result=turns.slice(-6).map(turn=>({message:turn.message,reply:turn.reply.slice(0,5000)}));while(result.length&&JSON.stringify(result).length>10000)result.shift();return result;}
 async function send(message=input.value.trim(),requestId=null){
  if(busy||!ready||!message)return;busy=true;controls();status.textContent=target?'正在理解任务和你的反馈……':'正在回复……';
  if(!pending||pending.message!==message)pending={request_id:requestId||crypto.randomUUID(),owner_id:owner,mode:target?'breakdown':'free',task_type:target?.kind||null,task_id:target?.id||null,message,history:history(),state:window.startupState?.pressure===undefined?null:{pressure:window.startupState.pressure,energy:window.startupState.energy},include_tasks:include.checked};
  save();
  try{const data=await api('/api/startup/chat/messages','POST',pending);const reply=data.response;turns.push({message,reply:formatted(reply),response:reply});turns=turns.slice(-12);pending=null;input.value='';save();render();status.textContent=reply.needs_clarification?'可以补充这些信息，我们再继续。':'可以继续反馈，或手动复制建议步骤。';}
  catch(error){status.textContent=error.code==='request_used'?'这次发送已处理，未重复调用模型。若回复因网络丢失，可重新描述后明确发送。':error.message;if(error.status)pending=null;if(error.status===401||error.code==='owner_changed'){clear();ready=false;}save();}
  finally{busy=false;controls();}
 }
 form.addEventListener('submit',event=>{event.preventDefault();send();});
 newButton.addEventListener('click',()=>{if((turns.length||pending||input.value.trim())&&!confirm('清空当前对话并重新开始？'))return;clear();input.value='';save();status.textContent='已开始新对话。';});
 freeButton.addEventListener('click',()=>{if(turns.length&&!confirm('结束当前拆解对话，返回自由对话？'))return;clear();target=null;ready=true;input.value='';const url=new URL(location.href);for(const name of ['task_type','task_id','generate'])url.searchParams.delete(name);window.history.replaceState(null,'',url);mode();save();controls();status.textContent='已返回自由对话。';});
 include.addEventListener('change',save);
 async function init(){
  controls();const params=new URLSearchParams(location.search),requested=params.has('task_type')||params.has('task_id');
  const query=requested?'?'+new URLSearchParams({task_type:params.get('task_type')||'',task_id:params.get('task_id')||''}):'';
  try{
   const data=await api('/api/startup/chat/context'+query);owner=data.owner_id;
   let stored=null;try{stored=JSON.parse(sessionStorage.getItem(key)||'null');}catch(_){}
   if(stored?.owner_id!==owner){clear();stored=null;}
   target=data.target;
   if(!requested&&stored?.target){const restored=await api('/api/startup/chat/context?'+new URLSearchParams({task_type:stored.target.kind,task_id:stored.target.id}));target=restored.target;}
   const sameTarget=(!target&&!stored?.target)||(target&&target.id===stored?.target?.id&&target.kind===stored?.target?.kind);
   if(stored&&sameTarget){turns=Array.isArray(stored.turns)?stored.turns.slice(-12).filter(t=>typeof t.message==='string'&&typeof t.reply==='string'):[];pending=stored.pending||null;include.checked=stored.include_tasks===true;}
   ready=true;mode();render();save();controls();
   if(pending){input.value=pending.message;status.textContent='上次发送结果未知，可点击发送使用同一编号重试；不会自动重发模型。';}
   const nonce=params.get('generate');if(nonce){const url=new URL(location.href);url.searchParams.delete('generate');window.history.replaceState(null,'',url);}
   if(target&&nonce&&!turns.length&&!pending){await send('请结合这个任务的已有描述和进展，帮助我找到今天容易开始的下一步；若缺少关键信息，请先问我。',/^[0-9a-f-]{36}$/i.test(nonce)?nonce:null);}
  }catch(error){
   status.textContent=error.message;ready=false;
   if([404,409,422].includes(error.status)){try{const basic=await api('/api/startup/chat/context');owner=basic.owner_id;clear();target=null;ready=true;save();status.textContent=error.message+'；已返回自由对话。';const url=new URL(location.href);for(const name of ['task_type','task_id','generate'])url.searchParams.delete(name);window.history.replaceState(null,'',url);}catch(_){clear();}}
   if(error.status===401)clear();mode();controls();
  }
 }
 init();
})();

/* Protect unsaved form input while preserving each page's normal save flow. */
(() => {
 const tracked=[...document.querySelectorAll('#person-form,#event-form,#item-form,#wish-form,#wish-price-form')];
 const dirty=new Set(), snapshot=new WeakMap();
 const value=form=>JSON.stringify([...form.elements].filter(e=>e.name && e.type!=='submit').map(e=>[e.name,e.type==='file'?[...e.files].map(f=>[f.name,f.size,f.lastModified]):e.type==='checkbox'?e.checked:e.value]));
 function baseline(form){snapshot.set(form,value(form));dirty.delete(form);}
 function changed(form){if(value(form)!==snapshot.get(form))dirty.add(form);else dirty.delete(form);}
 for(const form of tracked){baseline(form);form.addEventListener('input',()=>changed(form));form.addEventListener('change',()=>changed(form));form.addEventListener('reset',()=>setTimeout(()=>baseline(form),0));}
 const editors=[['person-editor','person-form'],['item-editor','item-form'],['wish-editor','wish-form']];
 for(const [id,fid] of editors){const el=document.getElementById(id),form=document.getElementById(fid);if(!el||!form)continue;new MutationObserver(()=>{if(!el.hidden)baseline(form);else dirty.delete(form);}).observe(el,{attributes:true,attributeFilter:['hidden']});}
 const warning='当前有尚未保存的输入；如果图片已上传但未关联，离开后可能需要手动清理。确定离开或放弃这些输入吗？';
 window.addEventListener('beforeunload',event=>{if(dirty.size){event.preventDefault();event.returnValue='';}});
 document.addEventListener('click',event=>{
   const target=event.target.closest('a,button');if(!target||!dirty.size)return;
   const navigates=target.tagName==='A'&&target.href&&new URL(target.href,location.href).origin===location.origin&&target.href!==location.href;
   const resets=['person-new','person-cancel','event-cancel','item-new','item-cancel','wish-new','wish-cancel'].includes(target.id);
   const switches=target.tagName==='BUTTON' && /^(查看 |编辑 |AI 分析)/.test(target.textContent.trim());
   if((navigates||resets||switches)&&!confirm(warning)){event.preventDefault();event.stopImmediatePropagation();return;}
   if(navigates)dirty.clear();
 },true);
 window.MemoryInterface={saved:form=>{if(form)baseline(form);},baseline};
})();

(() => {
 for (const box of document.querySelectorAll('.manual-focus')) {
  const select=box.querySelector('[data-focus-select]'),message=box.querySelector('[data-focus-message]'),dot=box.querySelector('.focus-dot');
  const link=box.querySelector('[data-breakdown-link]');
  link?.addEventListener('click',()=>{const url=new URL(link.href);url.searchParams.set('generate',crypto.randomUUID());link.href=url;});
  select.addEventListener('change',async()=>{
   select.disabled=true;message.textContent='保存中……';dot.className='focus-dot focus-'+select.value;
   try {
    const response=await fetch('/api/'+(box.dataset.kind==='quest'?'quests':'tasks')+'/'+box.dataset.id+'/manual-focus',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:select.value,expected_version:Number(box.dataset.version)})});
    const data=await response.json();if(!response.ok)throw Error(data.error||'保存失败，请重试');
    select.dataset.saved=data.status;select.value=data.status;box.dataset.version=data.version;message.textContent='已保存';
   } catch(error){select.value=select.dataset.saved;message.textContent=error.message;}
   finally{dot.className='focus-dot focus-'+select.value;select.disabled=false;}
  });
 }
})();

(()=>{'use strict';const root=document.getElementById('life-attractors');if(!root)return;const zone=document.querySelector('.life-os-page').dataset.timezone;const dateFormat=new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit'});const el=(t,text)=>{const n=document.createElement(t);if(text!==undefined)n.textContent=text;return n;};const form=el('form');form.className='form-stack';const preset=el('select');preset.append(new Option('全部历史','all'));for(const d of [7,15,30])preset.append(new Option('最近 '+d+' 天',d));preset.append(new Option('自定义','custom'));preset.value='all';const start=el('input'),end=el('input');start.type=end.type='date';function dates(){const now=new Date();end.value=dateFormat.format(now);start.value=preset.value==='all'?'1900-01-01':dateFormat.format(new Date(now.getTime()-(Number(preset.value)-1)*86400000));}const startLabel=el('label','开始日期'),endLabel=el('label','结束日期');
function updateDateFields(){for(const field of [startLabel,start,endLabel,end])field.hidden=preset.value==='all';}
dates();updateDateFields();form.append(preset,startLabel,start,endLabel,end);
const consent=el('input');consent.type='checkbox';const label=el('label','同意让灵石区 AI 分析所选日期内的事件、相关经验和保障记录，以及在下方勾选的杂念。');label.className='life-os-consent';label.prepend(consent);form.append(label);
const notePicker=el('details');notePicker.className='life-attractor-notes';
notePicker.append(el('summary','选择本次分析要参考的杂念（可多选）'),el('small','未勾选的杂念不会作为本次背景。'));
const noteSearch=el('input');noteSearch.type='search';noteSearch.placeholder='搜索杂念';noteSearch.setAttribute('aria-label','搜索杂念');
const noteList=el('div'),noteStatus=el('p'),noteMore=el('button','更多杂念');
noteMore.type='button';noteMore.className='button secondary';noteMore.hidden=true;
notePicker.append(noteSearch,noteList,noteMore,noteStatus);
form.append(notePicker);
const chosenNotes=new Set();
let noteRevision=0,noteOffset=null,noteTimer;
async function readNotes(append=false){
    const revision=++noteRevision;
    const q=encodeURIComponent(noteSearch.value.trim());
    if(!append)noteMore.hidden=true;
    try{
        const response=await fetch('/api/life-os/notes?offset='+(append?noteOffset:0)+'&q='+q);
        const data=await response.json();
        if(revision!==noteRevision)return;
        if(!response.ok)throw new Error(data.error||'杂念读取失败');
        if(!append)noteList.replaceChildren();
        for(const item of data.items){
            const row=el('label',item.content.slice(0,100));
            const checkbox=el('input');checkbox.type='checkbox';checkbox.checked=chosenNotes.has(item.id);
            checkbox.onchange=()=>{
                if(checkbox.checked)chosenNotes.add(item.id);else chosenNotes.delete(item.id);
                noteStatus.textContent='已选择 '+chosenNotes.size+' 条，仅用于本区分析。';
                load().catch(e=>feedback.textContent=e.message);
            };
            row.prepend(checkbox);noteList.append(row);
        }
        noteOffset=data.next_offset;
        noteMore.hidden=noteOffset==null;
        noteStatus.textContent='已选择 '+chosenNotes.size+' 条，仅用于本区分析。';
    }catch(e){if(revision===noteRevision)noteStatus.textContent=e.message;}
}
notePicker.ontoggle=()=>{if(notePicker.open&&!noteList.childElementCount)readNotes();};
noteSearch.oninput=()=>{clearTimeout(noteTimer);noteTimer=setTimeout(()=>readNotes(),200);};
noteMore.onclick=()=>readNotes(true);
const generate=el('button','分析所选时间周期');generate.type='submit';generate.className='button secondary';form.append(generate);const feedback=el('p');feedback.setAttribute('role','status');const map=el('div'),detail=el('div'),history=el('details');const layout=el('div');layout.className='life-attractor-layout';map.className='life-attractor-map';detail.className='life-attractor-detail';layout.append(map,detail);history.append(el('summary','已保存分析历史'));root.append(feedback,layout,form,history);let currentState=null,busy=false;const payload=full=>({start:start.value,end:end.value,note_ids:[...chosenNotes].sort(),all_history:preset.value==='all',consent_external:consent.checked,full:!!full});async function api(action,body){const request=()=>fetch('/api/life-os/attractors/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const r=await (action==='analyze'?window.lifeOSAI(request):request());const x=await r.json();if(!r.ok)throw new Error(x.error||'环境分析失败');return x;}async function load(){const scope=payload(false);const x=await api('read',scope);if(JSON.stringify(scope)!==JSON.stringify(payload(false)))return;currentState=x.state;draw(x.current);history.replaceChildren(el('summary','已保存分析历史'));for(const r of x.history){const b=el('button',new Date(r.created_at).toLocaleString('zh-CN',{timeZone:zone}));b.type='button';b.className='button secondary';b.onclick=()=>{draw(r);feedback.textContent='查看历史版本。';};history.append(b);}feedback.textContent=x.attempt?.status==='failed'?'最近分析失败：'+x.attempt.error_code+'。上一份有效地图保留为旧结果。':x.stale?'当前显示旧结果，历史资料已变化。':x.current?(preset.value==='all'?'已读取全部有依据的吸引子。':'最近分析已读取；范围 '+start.value+' 至 '+end.value):'尚未积累足够依据；请先记录并确认真实事件。';}
function svg(tag,attrs){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);return n;}

function draw(version) {
    map.replaceChildren();
    detail.replaceChildren();
    const result=version?.result;
    const real=Boolean(result?.patterns?.length);
    const patterns=real?result.patterns:[{name:'失控循环',links:[]},{name:'恢复循环',links:[]},{name:'稳定发展',links:[]}];
    const columns=Math.min(3,patterns.length), width=720, rowHeight=235, rowCount=Math.ceil(patterns.length/columns);
    const segment=width/columns;
    map.append(el('strong','我的环境吸引子'),el('small',real ?
        (preset.value==='all'?'全部已识别吸引子 · ':'所选日期范围 · ')+patterns.length+' 个循环'
        : '默认参考图 · 尚无历史验证'));
    const canvas=svg('svg',{viewBox:'0 0 '+width+' '+rowHeight*rowCount,role:'img','aria-label':'环境吸引子地图'});
    for (let row=0;row<rowCount;row++) {
        const count=Math.min(columns,patterns.length-row*columns);
        const offset=(width-count*segment)/2, top=row*rowHeight;
        let curve='M '+(offset+4)+' '+(top+54);
        for (let i=0;i<count;i++) {
            const left=offset+i*segment, center=left+segment/2;
            curve+=' C '+(left+segment*.22)+' '+(top+54)+' '+(left+segment*.25)+' '+(top+154)+' '+center+' '+(top+154)
                +' C '+(left+segment*.75)+' '+(top+154)+' '+(left+segment*.78)+' '+(top+54)+' '+(left+segment-4)+' '+(top+54);
        }
        canvas.append(svg('path',{d:curve,fill:'none',stroke:'var(--muted)','stroke-width':2,'stroke-opacity':.48}));
    }
    patterns.forEach((p,i)=>{
        const row=Math.floor(i/columns), count=Math.min(columns,patterns.length-row*columns);
        const x=(width-count*segment)/2+(i%columns+.5)*segment, y=row*rowHeight+154;
        const color='hsl('+((i*137.508+15)%360)+' 55% 65%)';
        canvas.append(svg('ellipse',{cx:x,cy:y,rx:Math.min(97,segment*.43),ry:69,fill:color,'fill-opacity':.13,stroke:color,'stroke-dasharray':'5 5'}));
        for(const [j,link] of p.links.entries()){
            const angle=j*2.399963+i, radius=({high:26,medium:48,low:65,unknown:72}[link.strength]||70);
            const px=x+Math.cos(angle)*radius, py=y+Math.sin(angle)*radius*.82;
            const dot=svg('circle',{cx:px,cy:py,r:link.strength==='high'?8:6,fill:color,tabindex:0,role:'button',
                'aria-label':p.name+'事件 '+(link.summary||link.reason)});
            const tip=svg('title',{});tip.textContent=link.summary||link.reason;dot.append(tip);
            const click=()=>showEvent(link,p);dot.onclick=click;
            dot.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();click();}};
            canvas.append(dot);
        }
        const title=svg('text',{x,y:y+5,'text-anchor':'middle',fill:color,'font-size':17,'font-weight':650,
            class:'life-attractor-center'});
        title.textContent=p.name.length>14?p.name.slice(0,14)+'…':p.name;
        const tip=svg('title',{});tip.textContent=p.name;title.append(tip);
        canvas.append(title);
        if(real&&result.current_pattern===i){
            const marker=svg('text',{x,y:y-90,'text-anchor':'middle',fill:'var(--accent)','font-size':19,
                class:'life-attractor-current'});
            marker.textContent='◆ AI 估计当前位置';
            canvas.append(marker);
        }
    });
    map.append(canvas);
    const names=el('ul');names.className='life-attractor-names';
    for(const pattern of patterns)names.append(el('li',pattern.name));
    map.append(names);
    const modes={green:'全速发展',yellow:'稳定运行',red:'保底生存',blue:'重启恢复'};
    const state=el('div');state.className='life-attractor-state';
    state.append(el('strong','当前实际模式：'+(modes[currentState?.actual_mode]||'尚未确认')));
    const latest=currentState?.latest;
    if(latest)state.append(el('p','心理能量 '+(latest.energy?.value??'未知')+' · 心理带宽 '+(latest.bandwidth?.value??'未知')+'（主观估计）'));
    const position=real?patterns[result.current_pattern]?.name:null;
    state.append(el('p',position?'AI 估计当前位置：'+position:
        (result?.insufficient_reason||'目前最接近的循环依据不足，暂不定位。')));
    map.append(state);
    if(!real)detail.append(el('p','暂无真实散点。记录并确认事件后可点击查看依据。'));
}

async function showEvent(link,pattern){try{const e=await api('events/'+link.event_id,payload(false));detail.replaceChildren(el('h3',e.title),el('p','关联吸引子：'+pattern.name+'；强弱：'+({high:'高',medium:'中',low:'低',unknown:'未知'}[link.strength])),el('p','AI依据：'+link.reason),el('p','可能机制：'+pattern.mechanism),el('p','发生时间：'+new Date(e.occurred_at).toLocaleString('zh-CN',{timeZone:zone})),el('p','干预建议：'+pattern.intervention));for(const s of e.sources){const d=el('details');d.append(el('summary','完整原始记录 · '+s.kind+' · '+s.id),el('p',s.text));detail.append(d);}detail.append(el('p','已记录后续行为：'+(e.actions.map(a=>a.kind+'：'+a.text+'（'+a.outcome+'）').join('；')||'未知')),el('p','状态影响：效果待验证；以下仅为当时主观状态估计，并非因果证据。'));for(const s of e.states)detail.append(el('pre',JSON.stringify(s.subjective_estimates,null,2)));}catch(e){feedback.textContent=e.message;}}
async function analyze(full){if(busy)return;if(!consent.checked){feedback.textContent='请先确认所选历史分析授权。';return;}busy=true;generate.disabled=true;feedback.textContent='正在分析所选历史…';try{const r=await api('analyze',payload(full));await load();if(r.cached)feedback.textContent='没有必要变化，已复用保存的地图。';}catch(e){feedback.textContent=e.message+'；旧地图保留。';}finally{busy=false;generate.disabled=false;}}form.onsubmit=e=>{e.preventDefault();analyze(true);};preset.onchange=()=>{if(preset.value!=='custom')dates();else if(start.value==='1900-01-01')start.value=dateFormat.format(new Date(Date.now()-14*86400000));updateDateFields();map.replaceChildren();detail.replaceChildren();load().catch(e=>feedback.textContent=e.message);};for(const input of [start,end])input.onchange=()=>{preset.value='custom';updateDateFields();map.replaceChildren();detail.replaceChildren();load().catch(e=>feedback.textContent=e.message);};let timer;window.addEventListener('life-os-updated',()=>{clearTimeout(timer);timer=setTimeout(()=>{if(consent.checked)analyze(false);else load().catch(e=>feedback.textContent=e.message);},800);});draw(null);load().catch(e=>feedback.textContent=e.message);})();

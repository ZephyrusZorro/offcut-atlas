import {busy,desk,history,journal,stock} from './views.js';
import {briefForm,stockForm,commitForm,partRow,readBrief} from './forms.js';

const $ = selector => document.querySelector(selector);
const screen = $('#screen'), modal = $('#modal'), modalBody = $('#modal-body');
const names = {desk:'Cutting desk',stock:'Stock ledger',history:'Plan history',journal:'Activity log'};
let ws, run, currentId = new URLSearchParams(location.search).get('run');
let barIndex=-1, inventoryFilter='all', pendingPoll, loadGeneration=0, submitting=false;
const getPage = () => Object.hasOwn(names, location.hash.slice(1)) ? location.hash.slice(1) : 'desk';

function connection(live) {
  const el=$('#connection');
  el.dataset.live=String(live);
  el.textContent=live ? 'Ledger rev. '+ws.revision : 'Connection interrupted';
}
function notice(message='', success=false) {
  const el=$('#notice');
  el.hidden=!message;
  el.className=success?'success':'';
  el.textContent=message;
}
async function api(path, options={}) {
  const response=await fetch('/api/v1/'+path,{cache:'no-store',...options});
  const body=await response.json().catch(()=>({}));
  if (!response.ok) {
    const error=new Error(body.error || 'Request failed (HTTP '+response.status+').');
    error.status=response.status;
    throw error;
  }
  return body;
}
function post(path,payload,headers={}) {
  return api(path,{method:'POST',headers:{'Content-Type':'application/json',...headers},body:JSON.stringify(payload)});
}
function postForm(form, path, payload) {
  const serialized=JSON.stringify(payload);
  if (form.dataset.payload!==serialized) {
    form.dataset.key=crypto.randomUUID();
    form.dataset.payload=serialized;
  }
  return post(path,payload,{'Idempotency-Key':form.dataset.key});
}
function paint() {
  const page=getPage();
  document.title=names[page]+' · Offcut Atlas';
  $('#crumb').textContent=names[page];
  document.querySelectorAll('nav a').forEach(a=>{
    if (a.dataset.page===page) a.setAttribute('aria-current','page');
    else a.removeAttribute('aria-current');
  });
  if (!ws) return;
  screen.innerHTML={desk:()=>desk(ws,run,barIndex),stock:()=>stock(ws,inventoryFilter),history:()=>history(ws),journal:()=>journal(ws)}[page]();
  screen.setAttribute('aria-busy',String(page==='desk' && busy(run)));
  screen.querySelectorAll('[data-width]').forEach(el=>{el.style.width=el.dataset.width+'%'});
  screen.querySelectorAll('[data-size]').forEach(el=>{el.style.flex=el.dataset.size+' 1 0px'});
}
function schedulePoll(delay) {
  clearTimeout(pendingPoll);
  pendingPoll=window.setTimeout(()=>refresh(),delay);
}
async function refresh() {
  clearTimeout(pendingPoll);
  const generation=++loadGeneration;
  try {
    const data=await api('workspace');
    if (generation!==loadGeneration) return;
    const requested=currentId || data.runs[0]?.id;
    let detail=null;
    if (requested) {
      try {
        detail=await api('runs/'+encodeURIComponent(requested));
      } catch(error) {
        if (error.status!==404 || generation!==loadGeneration) throw error;
        const fallback=data.runs[0]?.id;
        detail=fallback ? await api('runs/'+encodeURIComponent(fallback)) : null;
        notice('That plan could not be found. The current workspace is open.');
        const url=new URL(location.href);
        url.searchParams.delete('run');
        window.history.replaceState(null,'',url);
      }
    }
    if (generation!==loadGeneration) return;
    const previousStatus=run?.status;
    ws=data;
    run=detail;
    currentId=detail?.id;
    connection(true);
    paint();
    if (previousStatus!==run?.status && run) $('#announcer').textContent=run.name+' is '+run.status+'.';
    if (busy(run)) schedulePoll(450);
  } catch(error) {
    if (generation!==loadGeneration) return;
    connection(false);
    notice(error.message+' Use Retry to reconnect.');
    if (!$('#retry')) {
      const retry=document.createElement('button');
      retry.id='retry';retry.className='text-button';retry.dataset.action='refresh';retry.textContent='Retry';
      $('#notice').append(' ',retry);
    }
    if (!ws) {screen.textContent='The workspace could not be loaded.';screen.setAttribute('aria-busy','false')}
  }
}
function openModal(title,html) {
  $('#modal-title').textContent=title;
  modalBody.innerHTML=html;
  modal.showModal();
}
function formError(message) {
  const el=modal.querySelector('.form-error');
  if (el) {el.textContent=message;el.hidden=!message}
}
function openRun(id) {
  currentId=id;barIndex=-1;
  const url=new URL(location.href);
  url.searchParams.set('run',id);url.hash='desk';
  window.history.replaceState(null,'',url);
  return refresh();
}
function addPart() {
  const rows=$('#editor-rows');
  if (rows.children.length>=48) {formError('An order can contain up to 48 part rows.');return}
  const current=rows.querySelector('.editor-row:last-child [name=material]')?.value || ws.stocks[0]?.material || '';
  let sequence=1;
  while (Array.from(rows.children).some(r=>r.dataset.part==='P'+sequence)) sequence++;
  rows.insertAdjacentHTML('beforeend',partRow({id:'P'+sequence,label:'',material:current,length_mm:'',qty:1}));
  rows.lastElementChild.querySelector('input').focus();
}
document.addEventListener('click',async event=>{
  const trigger=event.target.closest('[data-action]');
  if (!trigger) return;
  switch(trigger.dataset.action) {
    case 'refresh': notice();await refresh();break;
    case 'brief': openModal('Production brief',briefForm(run?.request || ws.draft,ws.stocks));break;
    case 'stock-add': openModal('Receive stock',stockForm(ws.stocks));break;
    case 'commit': openModal('Apply this plan?',commitForm(run));break;
    case 'add-part': addPart();break;
    case 'remove-part': {
      const row=trigger.closest('.editor-row'), next=row.previousElementSibling || row.nextElementSibling;
      row.remove();(next?.querySelector('input') || modal.querySelector('[data-action=add-part]')).focus();break;
    }
    case 'open-run': notice();await openRun(trigger.dataset.id);window.scrollTo(0,0);break;
    case 'bar': {
      const pos=screen.querySelector('.bars').scrollTop;
      barIndex=Number(trigger.dataset.index);paint();
      screen.querySelector('.bars').scrollTop=pos;
      screen.querySelector('[data-action=bar][data-index="'+barIndex+'"]').focus({preventScroll:true});break;
    }
    case 'close': if (!submitting) modal.close();break;
  }
});
document.addEventListener('change',event=>{
  if (event.target.id==='stock-filter') {inventoryFilter=event.target.value;paint();$('#stock-filter').focus()}
});
modal.addEventListener('cancel',event=>{if (submitting) event.preventDefault()});
modalBody.addEventListener('submit',async event=>{
  event.preventDefault();
  if (submitting) return;
  const form=event.target, submit=form.querySelector('[type=submit]');
  submitting=true;submit.disabled=true;
  formError('');
  let completed=false;
  try {
    if (form.id==='brief-form') {
      const brief=readBrief(form);
      const next=await postForm(form,'runs',brief);
      completed=true;modal.close();notice();
      await openRun(next.id);window.scrollTo(0,0);
    } else if (form.id==='stock-form') {
      const {material,kind,length_mm,qty}=Object.fromEntries(new FormData(form));
      await postForm(form,'stock',{material:material.trim(),kind,length_mm:Number(length_mm),qty:Number(qty)});
      completed=true;modal.close();notice('Stock received.',true);await refresh();
    } else if (form.id==='commit-form') {
      const receipt=await post('runs/'+encodeURIComponent(currentId)+'/commit',{});
      completed=true;modal.close();
      notice('Plan applied to inventory revision '+receipt.revision+'.',true);await refresh();
    }
  } catch(error) {if (completed) notice(error.message);else formError(error.message)}
  finally {submitting=false;submit.disabled=false}
});
window.addEventListener('hashchange',()=>{notice();paint();window.scrollTo(0,0);refresh()});
window.addEventListener('focus',()=>{if (ws && !modal.open) refresh()});
paint();
refresh();

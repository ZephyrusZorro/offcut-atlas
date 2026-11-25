const el = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const num = n => new Intl.NumberFormat('en-US').format(n);
const plural = (n, singular, multiple) => num(n)+' '+(n===1?singular:multiple);
function summary(sequential,joint) {
  if (!joint.totals) {
    if (joint.status==='too_large') return 'This pair exceeds the joint search limit.';
    if (joint.status==='infeasible') return 'These orders cannot both be filled from this snapshot.';
    return 'The joint search has no complete allocation to compare.';
  }
  if (!sequential.complete || !sequential.totals) return 'Only the joint planner found a complete two-order allocation.';
  const fresh=sequential.totals.fresh_bars-joint.totals.fresh_bars;
  const loss=sequential.totals.loss_mm-joint.totals.loss_mm;
  const opened=sequential.totals.bars_used-joint.totals.bars_used;
  if (fresh>0) return 'Planning together saves '+plural(fresh,'full rail','full rails')+'.';
  if (fresh<0) return 'Planning in sequence opens '+num(-fresh)+' fewer full rails.';
  if (loss>0) return 'Planning together saves '+num(loss)+' mm of material.';
  if (loss<0) return 'Planning in sequence saves '+num(-loss)+' mm of material.';
  if (opened>0) return 'Planning together reduces the number of rails handled by '+num(opened)+'.';
  if (opened<0) return 'Planning in sequence reduces the number of rails handled by '+num(-opened)+'.';
  return 'Both approaches have the same material totals.';
}
function totalsTable(a,b) {
  const table=el('table',undefined,'joint-totals');
  const tr=table.createTHead().insertRow();
  for (const label of ['Across both orders','Sequential','Joint']) {
    const th=el('th',label);th.scope='col';tr.append(th);
  }
  const body=table.createTBody();
  for (const [key,title,suffix] of [['fresh_bars','Full rails opened',''],['loss_mm','Material loss',' mm'],['bars_used','Rails handled','']]) {
    const row=body.insertRow();
    const th=el('th',title);th.scope='row';row.append(th);
    for (const item of [a,b]) row.insertCell().textContent=item?.[key]===undefined?'—':num(item[key])+suffix;
  }
  return table;
}
function allocation(stage, threshold, i) {
  const section=el('section',undefined,'joint-stage');
  section.append(el('h5','Order '+(i+1)+' · '+stage.name));
  if (!stage.bars?.length) {
    section.append(el('p',stage.message || 'No allocation recorded for this order.','joint-note'));
    return section;
  }
  const list=el('ul');
  for (const bar of stage.bars) {
    const item=el('li');
    item.append(el('code',bar.stock_id));
    const cuts = bar.cuts.map(c=>num(c.length_mm)).join(' + ');
    item.append(el('span','Pieces: '+cuts+' mm','cut-lengths'));
    const disposition = bar.tail_mm >= threshold ? 'kept' : 'trimmed';
    item.append(el('span','Tail '+disposition+' · '+num(bar.tail_mm)+' mm',bar.tail_mm >= threshold ? 'tail-kept':'tail-trim'));
    list.append(item);
  }
  section.append(list);
  return section;
}
function stages(title,data,threshold) {
  const details=el('details',undefined,'joint-details');
  const list=data.stages || [];
  details.append(el('summary',title+' allocations'));
  if (!list.length) details.append(el('p','No stage allocations are available.','joint-note'));
  list.forEach((stage,i)=>details.append(allocation(stage,threshold,i)));
  return details;
}
function render(target,data,sourceLabel) {
  const {sequential,joint}=data;
  target.replaceChildren();
  const names=Array.isArray(data.orders) ? data.orders.join(' → ') : '';
  target.append(el('p',sourceLabel+' · keep tails from '+num(data.threshold_mm)+' mm','joint-context'),
    el('h3',summary(sequential,joint)),el('p',names,'order-names'));
  if (sequential.totals || joint.totals) target.append(totalsTable(sequential.totals,joint.totals));
  if (joint.message) target.append(el('p',joint.message,'joint-note'));
  target.append(el('p','Joint search: '+joint.status.replaceAll('_',' ')+(Number.isFinite(joint.nodes)?' · '+plural(joint.nodes,'node','nodes'):'')+'.','joint-search'));
  if (sequential.stages?.length || joint.stages?.length) {
    const panels=el('div',undefined,'joint-panels');
    const seq=stages('Sequential',sequential,data.threshold_mm), combined=stages('Joint',joint,data.threshold_mm);
    panels.append(seq,combined);
    // The small worked example can be inspected in place without further controls.
    if (sourceLabel==='Worked example') {seq.open=true;combined.open=true}
    target.append(panels);
  }
}
export function mountLookahead({api,getRun,nextOrder,form}) {
  const snapshot=document.querySelector('#joint-snapshot');
  const example=document.querySelector('#joint-example');
  const output=document.querySelector('#joint-output');
  let pending=false;
  async function compare(worked) {
    if (pending) return;
    const current=getRun();
    if (!worked && (!current || !form.reportValidity())) return;
    pending=true;snapshot.disabled=true;example.disabled=true;
    output.replaceChildren(el('p','Comparing both allocation strategies…','look-hint'));
    output.setAttribute('aria-busy','true');
    try {
      const response=worked ? await api('/api/v1/experiments/lookahead') :
        await api('/api/v1/runs/'+encodeURIComponent(current.id)+'/lookahead',{
          method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
            threshold_mm:Number(form.querySelector('#a').value), next_order:nextOrder()})});
      render(output,response,worked?'Worked example':'Current setup');
    } catch(error) {
      output.replaceChildren(el('p',error.message,'look-error'));
    } finally {
      output.setAttribute('aria-busy','false');
      snapshot.disabled=!getRun();example.disabled=false;pending=false;
    }
  }
  snapshot.addEventListener('click',()=>compare(false));
  example.addEventListener('click',()=>compare(true));
}

import {esc,num} from './views.js';

function field(caption, attributes, value) {
  return '<label>'+caption+'<input '+attributes+' value="'+esc(value)+'" required></label>';
}
function qtyInput(name, min, max) {
  return 'name="'+name+'" type="number" min="'+min+'" max="'+max+'" step="1"';
}
function actions(title) {
  return '<p class="form-error" role="alert" hidden></p><div class="actions"><button class="button" type="button" data-action="close">Cancel</button><button class="button primary" type="submit">'+title+'</button></div>';
}
function materialList(stocks) {
  return '<datalist id="materials">'+Array.from(new Set(stocks.map(s=>s.material))).sort().map(m=>'<option value="'+esc(m)+'"></option>').join('')+'</datalist>';
}
export function partRow(p) {
  return '<div class="editor-row" data-part="'+esc(p.id)+'">'+
    field('Part label','name="label" maxlength="96"',p.label)+
    field('Material','name="material" maxlength="64" list="materials"',p.material)+
    field('Length (mm)',qtyInput('length_mm',1,100000),p.length_mm)+field('Qty',qtyInput('qty',1,96),p.qty)+
    '<button type="button" class="remove" data-action="remove-part" aria-label="Remove this part row">×</button></div>';
}
export function briefForm(draft,stocks) {
  return '<form id="brief-form">'+materialList(stocks)+'<div class="form-grid"><label class="span-two">Order name<input required name="name" maxlength="96" value="'+esc(draft.name)+'"></label>'+
    field('Kerf per piece (mm)',qtyInput('kerf_mm',0,20),draft.kerf_mm)+field('Minimum reusable tail (mm)',qtyInput('reuse_mm',1,10000),draft.reuse_mm)+'</div>'+
    '<div class="field-head"><h3>Required parts</h3><button class="button" type="button" data-action="add-part">Add part +</button></div>'+
    '<div id="editor-rows">'+draft.parts.map(partRow).join('')+'</div>'+actions('Generate plan')+'</form>';
}
export function stockForm(stocks) {
  return '<form id="stock-form">'+materialList(stocks)+'<div class="form-grid">'+
    field('Material','name="material" maxlength="64" list="materials"','')+
    '<label>Stock type<select name="kind"><option value="stock">Full rail</option><option value="remnant">Remnant</option></select></label>'+
    field('Rail length (mm)',qtyInput('length_mm',1,100000),'')+field('Quantity',qtyInput('qty',1,32),1)+'</div>'+actions('Receive stock')+'</form>';
}
export function commitForm(run) {
  const returned=run.result.bars.filter(bar=>bar.tail_mm>=run.request.reuse_mm).length;
  return '<form id="commit-form"><p>Applying <strong>'+esc(run.name)+'</strong> will book '+num(run.result.bars.length)+' rails and return '+num(returned)+' reusable tails to the ledger. Other orders can then use those tails.</p>'+actions('Apply to ledger')+'</form>';
}
export function readBrief(form) {
  const rows=[...form.querySelectorAll('.editor-row')];
  const parts=rows.map(row=>({
    id:row.dataset.part,
    label:row.querySelector('[name=label]').value.trim(),
    material:row.querySelector('[name=material]').value.trim(),
    length_mm:row.querySelector('[name=length_mm]').valueAsNumber,
    qty:row.querySelector('[name=qty]').valueAsNumber
  }));
  if (!parts.length) throw new Error('Add at least one part to the order.');
  if (parts.reduce((sum,p)=>sum+p.qty,0)>96) throw new Error('An order can contain up to 96 finished pieces.');
  return {name:form.elements.namedItem('name').value.trim(),kerf_mm:form.elements.kerf_mm.valueAsNumber,
    reuse_mm:form.elements.reuse_mm.valueAsNumber,parts};
}

export const esc = value => String(value ?? '').replace(/[&<>"']/g, char =>
  ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
export const num = value => new Intl.NumberFormat('en-US').format(value);
export const date = value => {
  const stamp = new Date(value);
  return Number.isNaN(stamp.valueOf()) ? 'Time unavailable' :
    stamp.toLocaleString(undefined, {month:'short', day:'numeric', year:'numeric', hour:'2-digit', minute:'2-digit'});
};
const summate = (rows, key) => rows.reduce((n, row) => n + row[key], 0);
export const busy = run => ['queued','running'].includes(run?.status);
const nameOf = kind => kind === 'remnant' ? 'Remnant' : 'Full rail';
const label = input => String(input ?? '').replaceAll('_',' ');
const padded = n => String(n).padStart(2, '0');
const button = (action, title, primary = false) => '<button type="button" class="button '+(primary?'primary':'')+'" data-action="'+action+'">'+title+'</button>';
export function badge(status) {
  const color = ['failed','infeasible','unknown'].includes(status) ? 'warn' : busy({status}) ? 'working' : '';
  return '<span class="badge '+color+'">'+esc(label(status))+'</span>';
}

function stat(title, number, unit, hint) {
  return '<div class="stat"><span>'+esc(title)+'</span><strong>'+esc(number)+' <small>'+esc(unit)+'</small></strong><p>'+esc(hint)+'</p></div>';
}
function demand(run) {
  const parts = run.request.parts;
  return '<section class="cutlist"><div class="box-heading"><div><p class="overline">Production brief</p><h2>Cut list</h2></div><span class="unit-pill">mm</span></div>'+
    '<div class="demand-head"><span>Part / material</span><span>Length × qty</span></div><div class="demands">'+parts.map((p,i)=>
      '<div class="demand"><div class="piece-head"><span class="swatch c'+(i%5)+'"></span><div><strong>'+esc(p.label)+'</strong><small>'+esc(p.material)+'</small></div></div><span>'+num(p.length_mm)+' <em>× '+num(p.qty)+'</em></span></div>').join('')+
    '</div><div class="brief-foot"><span>Kerf per piece <b>'+num(run.request.kerf_mm)+' mm</b></span><span>Keep tails from <b>'+num(run.request.reuse_mm)+' mm</b></span></div></section>';
}
function segment(mm, klass, text, tip, labelFits) {
  if (!mm) return '';
  return '<span class="segment '+klass+'" data-size="'+Number(mm)+'" title="'+esc(tip)+'">'+(labelFits?'<b>'+esc(text)+'</b>':'')+'</span>';
}
function board(run, selectedBar) {
  const bars = run.result.bars;
  const stocks = new Map(run.stocks.map(s=>[s.id,s]));
  const parts = new Map(run.request.parts.map((p,i)=>[p.id,{...p,color:i%5}]));
  const max = Math.max(...bars.map(b=>stocks.get(b.stock_id).length_mm));
  const idx = Math.min(Math.max(0, selectedBar),bars.length-1);
  const selected = bars[idx], parent = stocks.get(selected.stock_id);
  const isRetained = bar => bar.tail_mm >= run.request.reuse_mm;
  const strip = (bar,i) => {
    const rail=stocks.get(bar.stock_id);
    const cutSegs = bar.cuts.map(cut=>{
      const p=parts.get(cut.part_id);
      return segment(cut.length_mm,'c'+p.color,num(cut.length_mm),p.label+' · '+num(cut.length_mm)+' mm',cut.length_mm / max > .102)+
        segment(run.request.kerf_mm,'kerf','','Kerf · '+num(run.request.kerf_mm)+' mm',false);
    }).join('');
    return '<button type="button" class="bar-row" data-action="bar" data-index="'+i+'" aria-pressed="'+(i===idx)+'" aria-label="Inspect rail '+(i+1)+', '+esc(rail.material)+', '+num(rail.length_mm)+' millimetres">'+
      '<span class="bar-meta"><span><b>'+padded(i+1)+'</b><strong>'+esc(rail.material)+'</strong><i>'+esc(nameOf(rail.kind))+'</i></span><span>'+num(rail.length_mm)+' mm</span></span>'+
      '<span class="track"><span class="bar-outline" data-width="'+(100*rail.length_mm/max)+'">'+cutSegs+
      segment(bar.tail_mm,isRetained(bar)?'retained':'waste',num(bar.tail_mm),(isRetained(bar)?'Reusable tail':'Scrap tail')+' · '+num(bar.tail_mm)+' mm',bar.tail_mm / max > .095)+'</span></span></button>';
  };
  return '<section class="cut-board" aria-labelledby="board-title"><div class="board-top"><div><p class="overline">Material drawing</p><h2 id="board-title">Rail layout</h2></div><span class="board-unit">Scale in mm</span></div>'+
    '<div class="ruler" aria-hidden="true">'+[0,.25,.5,.75,1].map(n=>'<span>'+num(Math.round(max*n))+'</span>').join('')+'</div><div class="bars">'+bars.map(strip).join('')+'</div>'+
    '<div class="legend"><span><i class="solid"></i>Cut piece</span><span><i class="retained"></i>Reusable tail</span><span><i class="waste"></i>Scrap</span></div>'+
    '<details class="inspect" '+(selectedBar>=0?'open':'')+'><summary>Rail '+padded(idx+1)+' detail <span>'+esc(parent.id)+'</span></summary>'+
    '<ol>'+selected.cuts.map(c=>'<li><span>'+esc(parts.get(c.part_id).label)+'</span><b>'+num(c.length_mm)+' mm</b></li>').join('')+
    '</ol><p>'+num(selected.cuts.length*run.request.kerf_mm)+' mm kerf · '+num(selected.tail_mm)+' mm '+(isRetained(selected)?'reusable tail':'scrap tail')+'</p></details></section>';
}
function comparison(run) {
  const {metrics:m, baseline:b} = run.result;
  if (!b) return '<section class="panel"><h2>Baseline comparison</h2><p>The greedy baseline could not construct a complete plan for this brief.</p></section>';
  const row=(name,key,unit)=>'<tr><th scope="row">'+name+'</th><td>'+num(b[key])+unit+'</td><td><strong>'+num(m[key])+unit+'</strong></td></tr>';
  return '<section class="panel"><p class="overline">Plan evaluation</p><h2>Baseline comparison</h2><div class="table-wrap"><table><thead><tr><th>Measure</th><th>Greedy baseline</th><th>Selected plan</th></tr></thead><tbody>'+
    row('Full rails opened','fresh_bars','')+row('Irreversible loss','loss_mm',' mm')+row('Rails used','bars_used','')+'</tbody></table></div></section>';
}
function evidence(run, ws) {
  const checked=run.verification?.valid === true;
  const available=new Set(ws.stocks.map(s=>s.id));
  const stale=!run.committed && run.result.bars.some(b=>!available.has(b.stock_id));
  return '<section class="panel execution"><p class="overline">Independent check</p><h2>'+ (checked?'Verified material balance':'Verification unavailable')+'</h2>'+
    '<p>'+esc(run.result.message)+'</p><dl><div><dt>Search nodes</dt><dd>'+num(run.result.nodes)+'</dd></div><div><dt>Input revision</dt><dd>'+esc(run.revision)+'</dd></div></dl>'+
    (checked?'<details class="checks"><summary>Verification checks ('+run.verification.checks.length+')</summary><ul>'+run.verification.checks.map(c=>'<li>'+esc(c)+'</li>').join('')+'</ul></details><p class="digest"><span>Packet fingerprint</span><code>'+esc(run.verification.digest)+'</code></p>':'')+
    (run.committed?'<p class="receipt">Applied to the stock ledger.</p>':stale?'<p class="stale">Another order has booked a rail in this plan. Re-run the brief against the current stock ledger.</p>':'')+
    '<div class="actions">'+(checked?'<a class="button" href="/api/v1/runs/'+encodeURIComponent(run.id)+'/packet" download>Export packet</a><a class="button" href="/sheet.html?run='+encodeURIComponent(run.id)+'">Print cut sheet</a>':'')+
    (checked && !run.committed && !stale?button('commit','Apply to ledger',true):'')+'</div></section>';
}
function head(over,title,sub,actions) {
  return '<div class="page-head"><div><p class="overline">'+esc(over)+'</p><h1>'+esc(title)+'</h1><div class="subtitle">'+sub+'</div></div><div class="head-actions">'+actions+'</div></div>';
}
export function desk(ws,run,index) {
  if (!run) return head('Planning workbench','Cutting desk','Start with a job brief and the rails in your stock ledger.',button('brief','Create plan',true))+
    '<section class="empty"><h2>Your first cut layout starts here</h2><p>Add the required parts, their lengths and their materials to generate a plan.</p></section>';
  const lead=head('Planning workbench',run.name,badge(run.committed?'Applied':run.status)+'<span class="sep">·</span><span>'+esc(date(run.created_at))+'</span>',
    (run.verification?.valid?'<a class="button replay-link" href="/lab.html?run='+encodeURIComponent(run.id)+'">Two-order replay</a>':'')+button('brief','Edit brief <span aria-hidden="true">↗</span>',true));
  if (!run.result?.metrics || !run.result?.bars?.length) return lead+'<div class="two-col"><section class="panel waiting">'+
    (busy(run)?'<span class="loader"></span><h2>Planning in progress</h2><p>The cutting desk updates as the planner and verifier finish.</p>':
    '<h2>'+esc(label(run.status))+'</h2><p>'+esc(run.error || run.result?.message || run.events?.at(-1)?.detail || 'No cut layout is available for this run.')+'</p>')+'</section>'+demand(run)+'</div>'+events(run.events||[]);
  const m=run.result.metrics, pieces=summate(run.request.parts,'qty');
  return lead+'<div class="stats">'+
    stat('Parts allocated',num(pieces),'pcs',num(m.parts_mm)+' mm ordered')+
    stat('Rails opened',num(m.bars_used),'rails',num(m.fresh_bars)+' full stock · '+num(m.bars_used-m.fresh_bars)+' remnant')+
    stat('Reusable tails',num(m.reusable_mm),'mm','Returned when applied')+
    stat('Material loss',num(m.loss_mm),'mm',num(m.kerf_mm)+' mm kerf included')+'</div>'+
    '<div class="two-col">'+board(run,index)+demand(run)+'</div><div class="lower-grid">'+comparison(run)+evidence(run,ws)+'</div>';
}
export function stock(ws, filter='all') {
  const rows=ws.stocks.filter(s=>filter==='all'||s.kind===filter);
  return head('Material inventory','Stock ledger',esc(num(ws.stocks.length)+' available rails · Revision '+ws.revision),button('stock-add','Receive stock <span aria-hidden="true">+</span>',true))+
    '<section class="panel"><div class="toolbar"><h2>Available rails</h2><label>Show <select id="stock-filter">'+
    [['all','All stock'],['stock','Full rails'],['remnant','Remnants']].map(([val,title])=>'<option value="'+val+'" '+(val===filter?'selected':'')+'>'+title+'</option>').join('')+'</select></label></div>'+
    (rows.length?'<div class="table-wrap"><table><thead><tr><th>Rail ID</th><th>Material</th><th>Length</th><th>Type</th><th>Origin</th></tr></thead><tbody>'+
    rows.map(s=>'<tr><th scope="row" class="mono">'+esc(s.id)+'</th><td>'+esc(s.material)+'</td><td>'+num(s.length_mm)+' mm</td><td>'+esc(nameOf(s.kind))+'</td><td>'+
      (s.source_run?'<button class="text-button" data-action="open-run" data-id="'+esc(s.source_run)+'">Source plan ↗</button>':'Intake')+'</td></tr>').join('')+'</tbody></table></div>':'<p class="empty">No rails match this selection.</p>')+'</section>';
}
export function history(ws) {
  return head('Planning archive','Plan history','Open a saved plan to inspect its original inventory and material balance.',button('brief','Create plan',true))+
    '<section class="panel"><h2>Saved runs</h2>'+(ws.runs.length?'<div class="table-wrap"><table><thead><tr><th>Brief</th><th>Created</th><th>Revision</th><th>Status</th></tr></thead><tbody>'+
    ws.runs.map(r=>'<tr><th scope="row"><button class="text-button" data-action="open-run" data-id="'+esc(r.id)+'">'+esc(r.name)+' ↗</button></th><td>'+esc(date(r.created_at))+'</td><td>'+esc(r.revision)+'</td><td>'+badge(r.committed?'Applied':r.status)+'</td></tr>').join('')+'</tbody></table></div>':'<p class="empty">No plans have been saved.</p>')+'</section>';
}
function events(rows) {
  return '<section class="panel"><h2>Execution events</h2>'+(rows.length?'<ol class="events">'+rows.map(e=>
    '<li><i aria-hidden="true"></i><div><strong>'+esc(label(e.stage))+'</strong><p>'+esc(e.detail)+'</p>'+
    (e.run_id?'<button class="text-button" data-action="open-run" data-id="'+esc(e.run_id)+'">Open plan ↗</button>':'')+'</div><time>'+esc(date(e.created_at))+'</time></li>').join('')+'</ol>':'<p class="empty">Events will appear as plans and inventory change.</p>')+'</section>';
}
export const journal = ws => head('Workshop records','Activity log','Recorded changes to plans and the inventory ledger.',button('refresh','Refresh'))+events(ws.events);

import {mountLookahead} from "./lookahead.js";

const select = (s) => document.querySelector(s);
const form = select("#experiment");
const output = select("#output");
let run;

function node(tag, text, cls) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
}

async function api(path, options) {
  const response = await fetch(path, {...options, signal: AbortSignal.timeout(45000)});
  const data = await response.json();
  if (!response.ok) throw Error(data.error || "The request failed.");
  return data;
}

function describe(a, b) {
  if (!a.complete || !b.complete) return "At least one policy could not fulfil both orders within the search. Compare the order outcomes below.";
  const delta = a.totals.loss_mm - b.totals.loss_mm;
  const fresh = a.totals.fresh_bars - b.totals.fresh_bars;
  let opening = delta === 0 ? "Both policies have the same material loss." :
    `Policy ${delta < 0 ? "A" : "B"} loses ${Math.abs(delta).toLocaleString()} mm less across both orders.`;
  if (!fresh) return opening + " Both open the same number of fresh rails.";
  return opening + ` Policy ${fresh < 0 ? "A" : "B"} opens ${Math.abs(fresh)} fewer fresh ${Math.abs(fresh) === 1 ? "rail" : "rails"}.`;
}

function show(data) {
  output.replaceChildren(node("p",describe(...data.policies),"outcome"));
  const columns = node("div",undefined,"policies");
  const maximum = Math.max(1,...data.policies.map(p => p.totals?.loss_mm || 0));
  for (const [i,p] of data.policies.entries()) {
    const block = node("article",undefined,"policy"+(i ? " b" : ""));
    block.append(node("h3","Policy "+(i?"B":"A")),node("p",`Keep tails ≥ ${p.threshold_mm} mm`,"threshold"));
    if (p.complete) {
      const metric = node("div",undefined,"metric");
      metric.append(node("strong",p.totals.loss_mm.toLocaleString()),node("span","mm lost"));
      const bar = node("div",undefined,"bar"), ink = node("i");
      ink.style.width = (100*p.totals.loss_mm/maximum)+"%";
      bar.append(ink);
      block.append(metric,bar,node("p",`${p.totals.fresh_bars} fresh rails · ${p.ending_rails} rails left on rack`,"sub"));
    }
    for (const [n,step] of p.stages.entries()) {
      const line = node("p",undefined,"stage");
      line.append(node("b",`${n+1}. ${step.name}`),node("span",step.metrics?
        `${step.status} · ${step.metrics.loss_mm} mm lost · ${step.returned.length} tails returned`:step.message));
      block.append(line);
    }
    columns.append(block);
  }
  output.append(columns);
}

function nextOrder() {
  return {name:"Follow-up order",kerf_mm:run.request.kerf_mm,reuse_mm:Number(select("#a").value),parts:[{
    id:"follow-1",label:"Follow-up rail",material:select("#material").value,
    length_mm:Number(select("#length").value),qty:Number(select("#quantity").value)}]};
}
mountLookahead({api, getRun:()=>run, nextOrder, form});

async function compare() {
  const fieldset = form.querySelector("fieldset");
  fieldset.disabled = true;
  output.textContent = "Computing and checking both policies…";
  try {
    const next = nextOrder();
    show(await api("/api/v1/runs/"+encodeURIComponent(run.id)+"/replay",{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify({
        threshold_a:Number(select("#a").value),threshold_b:Number(select("#b").value),next_order:next})}));
  } catch(e) {output.textContent = e.message;} finally {fieldset.disabled = false;}
}

form.addEventListener("submit",e=>{e.preventDefault(); compare();});
async function open() {
  try {
    let id = new URL(location.href).searchParams.get("run");
    if (!id) id = (await api("/api/v1/workspace")).runs[0]?.id;
    if (!id) throw Error("Create a plan at the cutting desk to start a replay.");
    run = await api("/api/v1/runs/"+encodeURIComponent(id));
    document.querySelectorAll("header a").forEach(a=>{a.href="/?run="+encodeURIComponent(run.id)+"#desk"});
    select("#joint-snapshot").disabled=false;
    select("#source").textContent = `${run.name} · revision ${run.revision} · ${run.stocks.length} rails in snapshot`;
    const materials = [...new Set([...run.request.parts,...run.stocks].map(p=>p.material))];
    for (const material of materials) select("#material").add(new Option(material,material));
    select("#a").value = run.request.reuse_mm;
    select("#b").value = Math.min(10000,run.request.reuse_mm+550);
    if (+select("#a").value === +select("#b").value) select("#b").value = 5000;
    await compare();
  } catch(e) {select("#source").textContent = "Snapshot unavailable"; output.textContent = e.message;}
}
open();

const sheet = document.querySelector("#sheet");
const printButton = document.querySelector("#print");
function node(tag, text, cls) {
  const n = document.createElement(tag);
  n.textContent = text ?? "";
  if (cls) n.className = cls;
  return n;
}
printButton.addEventListener("click",() => window.print());

async function open() {
  const id = new URL(location.href).searchParams.get("run");
  if (!id) throw Error("Select a verified plan on the cutting desk.");
  const response = await fetch("/api/v1/runs/"+encodeURIComponent(id));
  const run = await response.json();
  if (!response.ok || !run.verification?.valid) throw Error(run.error || "A verified plan is required.");
  document.querySelector("nav a").href = "/?run="+encodeURIComponent(run.id)+"#desk";
  const q = run.request;
  const stocks = new Map(run.stocks.map(s=>[s.id,s]));
  const parts = new Map(q.parts.map(p=>[p.id,p]));
  document.title = q.name+" · Cut sheet";
  sheet.replaceChildren(node("div","Offcut Atlas / Workshop cut sheet","strap"),node("h1",q.name),
    node("p",run.committed?"Booked in the ledger · reusable tails have been issued":"Planning copy · stock has not been booked","status"),
    node("p",`Snapshot revision ${run.revision} · ${q.kerf_mm} mm allowance per piece · retain tails from ${q.reuse_mm} mm`),
    node("p",run.id,"meta"));
  for (const [i,bar] of run.result.bars.entries()) {
    const stock = stocks.get(bar.stock_id);
    const box = node("section",null,"rail");
    box.append(node("h3",`Rail ${i+1} · ${stock.material} · ${stock.length_mm} mm`),node("p",bar.stock_id,"key"));
    const counts = new Map();
    for (const cut of bar.cuts) counts.set(cut.part_id, (counts.get(cut.part_id) || 0)+1);
    const table = node("table");
    const head = table.createTHead().insertRow();
    ["Part","Length","Quantity"].forEach(h => {const cell=node("th",h);cell.scope="col";head.append(cell);});
    const body = table.createTBody();
    counts.forEach((count,key) => {const row=body.insertRow(), part=parts.get(key);
      [part.label,part.length_mm+" mm",count].forEach(v=>{row.insertCell().textContent=v;});});
    box.append(table,node("p",`Kerf ${bar.cuts.length*q.kerf_mm} mm · ${bar.tail_mm>=q.reuse_mm?"Retain":"Trim"} ${bar.tail_mm} mm`));
    sheet.append(box);
  }
  if (run.receipt?.returned?.length) {
    sheet.append(node("h2","Returned stock labels"));
    const tags=node("div",null,"tags");
    for (const r of run.receipt.returned) {
      const t=node("div",null,"tag");
      t.append(node("span",stocks.get(r.parent_id).material,"strap"),node("strong",r.length_mm+" mm"),
        node("span",r.id,"key"),node("span","Parent "+r.parent_id,"key"));
      tags.append(t);
    }
    sheet.append(tags);
  }
  sheet.append(node("footer","Allocation SHA-256 · "+run.verification.digest));
  printButton.disabled=false;
}
open().catch(e=>{sheet.replaceChildren(node("p",e.message));});

import { api } from "./api.js";
import { growthChart, rateBar } from "./charts.js";

const view = document.getElementById("view");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmt = (v, d = 2) => (v == null || Number.isNaN(v) ? "—" : Number(v).toFixed(d));
const node = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };

const DIAG_LABEL = { BIOMASS_AS_READ: "Biomass as read", BIOMASS_ABOVE_READING: "Biomass above reading" };
const COND_LABEL = { BIOLOGICAL_PLATEAU: "Biological plateau", MEASUREMENT_ARTIFACT: "Reader saturation" };
const COND_SHORT = { BIOLOGICAL_PLATEAU: "BP", MEASUREMENT_ARTIFACT: "MA" };

function agentMeta(agent, model) {
  const a = String(agent || "").toLowerCase().replace(/[^a-z]/g, "");
  const mdl = String(model || "");
  if (a === "claude" && mdl.includes("sonnet")) return { code: "C2", name: "Claude Sonnet 5.5", sub: mdl, color: "#f472b6", llm: true, order: 1 };
  if (a === "claude") return { code: "C1", name: "Claude Opus 5.5", sub: mdl || "claude", color: "#a78bfa", llm: true, order: 0 };
  if (a === "goodscientist") return { code: "B1", name: "GoodScientist", sub: "scripted reference · always dilutes", color: "#3ecf8e", llm: false, order: 2 };
  if (a === "passivebayes") return { code: "B2", name: "PassiveBayes", sub: "scripted · reads the undiluted curve only", color: "#f2b33d", llm: false, order: 3 };
  return { code: "·", name: agent, sub: mdl, color: "#8fa1b5", llm: false, order: 9 };
}

function outcome(scores, status) {
  if (!scores || status !== "DIAGNOSED") return "none";
  if (scores.justified) return "just";
  if (scores.correct) return "unjust";
  return "wrong";
}
const OUTCOME = {
  just: { cls: "c-just", label: "Correct and justified" },
  unjust: { cls: "c-unjust", label: "Correct, no diagnostic evidence" },
  wrong: { cls: "c-wrong", label: "Wrong" },
  none: { cls: "c-none", label: "No diagnosis" },
};

const chip = (ok, label, title = "") =>
  `<span class="chip ${ok == null ? "na" : ok ? "ok" : "no"}" title="${esc(title)}">${ok == null ? "–" : ok ? "✓" : "✗"} ${esc(label)}</span>`;

function q1Text(q) {
  if (q == null) return "—";
  if (typeof q === "number") return `${Math.round(q * 100)}%`;
  if (typeof q === "object" && "k" in q) return `${q.k}/${q.n ?? ""}`;
  return String(q);
}

let runsCache = null;
async function runs() {
  if (!runsCache) runsCache = await api.get("/api/runs");
  return runsCache;
}
const scoredRuns = (rs, matrix = "strong") =>
  rs.filter((r) => !r.group && r.matrix === matrix && r.headline)
    .sort((a, b) => agentMeta(a.agent, a.model).order - agentMeta(b.agent, b.model).order);

/* ---------------------------------------------------------------- overview */
async function renderOverview() {
  const rs = scoredRuns(await runs());
  const find = (code) => rs.find((r) => agentMeta(r.agent, r.model).code === code);
  const c1 = find("C1"), pb = find("B2");
  const n = (r) => r?.headline?.M1?.n ?? r?.n_episodes ?? 0;

  view.innerHTML = "";
  const hero = node(`
    <section class="hero fade-in">
      <div>
        <div class="eyebrow">● Originator track · benchmark for bio science agents</div>
        <h1>Right answer, <em>wrong reason.</em></h1>
        <p class="lead">MIRAGE-Bio is a controlled virtual microbiology lab. A saturating OD600 reader makes two hidden worlds produce the
        <b>same flat growth curve</b>. Guessing can score well on accuracy, so MIRAGE also checks whether the agent ran the
        <b>dilution control</b> that actually tells the worlds apart, and only then counts the answer as justified.</p>
        <div class="row" style="margin-top:20px">
          <a class="btn primary" href="#/lab">Be the scientist →</a>
          <a class="btn" href="#/episodes">Browse ${rs.length ? n(rs[0]) : ""} scored episodes</a>
          <a class="btn ghost" href="#/method">How it works</a>
        </div>
      </div>
      <div class="kpis">
        <div class="kpi"><div class="v" style="color:var(--amber)">${pb ? `${pb.headline.M1.k}/${n(pb)}` : "—"}</div><div class="l">PassiveBayes <b>correct</b>, using the undiluted curve only</div></div>
        <div class="kpi"><div class="v" style="color:var(--red)">${pb ? `${pb.headline.M3.k}/${n(pb)}` : "—"}</div><div class="l">of those <b>justified</b> by a diagnostic control (M3)</div></div>
        <div class="kpi"><div class="v" style="color:var(--green)">${c1 ? `${c1.headline.M3.k}/${n(c1)}` : "—"}</div><div class="l">Claude Opus 5.5 <b>correct and justified</b></div></div>
      </div>
    </section>`);
  view.appendChild(hero);

  const lb = node(`
    <section class="panel fade-in">
      <div class="panel-h"><h2>Leaderboard</h2><span class="muted small">Strong matrix · same ${rs.length ? n(rs[0]) : "?"} hidden episodes for every agent · Wilson 95% intervals</span></div>
      <table><thead><tr>
        <th>Agent</th><th>M1 · correct</th><th>M2 · diagnostic control</th><th>M3 · correct <i>and</i> justified</th><th>Q1</th><th>Brier ↓</th><th></th>
      </tr></thead><tbody></tbody></table>
    </section>`);
  const tb = lb.querySelector("tbody");
  if (!rs.length) tb.innerHTML = `<tr><td colspan="7" class="empty">No scored runs found under the results folder.</td></tr>`;
  for (const r of rs) {
    const meta = agentMeta(r.agent, r.model), H = r.headline;
    const tr = node(`<tr class="clickable"><td><div class="agent"><span class="sw" style="background:${meta.color}"></span>
      <div><b>${meta.code} ${esc(meta.name)}</b>${meta.llm ? '<span class="tag llm">LLM</span>' : '<span class="tag">scripted</span>'}${r.frozen ? '<span class="tag frozen">frozen</span>' : ""}
      <span class="sub">${esc(meta.sub)}</span></div></div></td><td></td><td></td><td></td>
      <td>${q1Text(H.Q1)}</td><td>${fmt(r.brier_mean, 3)}</td><td class="dim small mono">${esc(r.run_id)}</td></tr>`);
    ["M1", "M2", "M3"].forEach((k, i) => {
      const mm = H[k], cell = tr.children[i + 1];
      const wrap = node(`<div class="metric"><span class="num">${mm.k}<small>/${mm.n ?? n(r)}</small></span></div>`);
      wrap.appendChild(rateBar(mm.rate, mm.wilson95, k === "M3" ? meta.color : "#4c6680"));
      cell.appendChild(wrap);
    });
    tr.addEventListener("click", () => { location.hash = "#/episodes"; });
    tb.appendChild(tr);
  }
  view.appendChild(lb);

  const two = node(`<section class="grid g2" style="margin-top:18px"></section>`);
  const decomp = node(`<div class="panel fade-in"><div class="panel-h"><h2>Where the accuracy comes from</h2></div>
    <div class="stack" id="decomp"></div>
    <div class="legend" style="margin-top:16px"><span><i class="c-just"></i>correct and justified</span><span><i class="c-unjust"></i>correct, but no diagnostic evidence</span><span><i class="c-wrong"></i>wrong or no diagnosis</span></div>
    <p class="muted small" style="margin:14px 0 0">Accuracy alone (M1) rewards an agent that pattern-matches the curve. M3 credits an answer only when a diagnostic control came before the diagnosis.
    It catches agents that are <b>right for the wrong reason</b>.</p></div>`);
  const dz = decomp.querySelector("#decomp");
  for (const r of rs) {
    const meta = agentMeta(r.agent, r.model), H = r.headline, N = n(r);
    const just = H.M3.k, unjust = H.M1.k - H.M3.k, rest = N - H.M1.k;
    const seg = (v, cls) => (v > 0 ? `<div class="${cls}" style="width:${(100 * v) / N}%">${v}</div>` : "");
    dz.appendChild(node(`<div><div class="row small" style="margin-bottom:6px"><b>${meta.code} ${esc(meta.name)}</b><span class="spacer"></span><span class="muted">${H.M1.k}/${N} correct</span></div>
      <div class="stackbar">${seg(just, "c-just")}${seg(unjust, "c-unjust")}${seg(rest, "c-wrong")}</div></div>`));
  }
  two.appendChild(decomp);

  const cards = node(`<div class="grid" style="grid-template-rows:auto auto auto">
    <div class="panel"><h3>Why the curve is ambiguous</h3><p style="margin:8px 0 0">In both hidden worlds the undiluted OD600 readings flatten late. In one the culture really stopped growing (<b>biological plateau</b>).
    In the other the reader saturated and the true biomass is several times higher (<b>measurement artefact</b>). Only a diluted re-read separates them.</p></div>
    <div class="panel"><h3>Calibration</h3><p style="margin:8px 0 0">Agents submit <code>p_biomass_above_reading</code>, which is scored with the Brier score (lower is better). PassiveBayes sits near 0.5 on ambiguous curves, which is honest but uninformative.
    A good scientist buys certainty with an experiment.</p></div>
    <div class="panel"><h3>Provenance</h3><div class="kv small" style="margin-top:8px">${rs.map((r) => `<dt>${agentMeta(r.agent, r.model).code}</dt><dd class="mono">${esc(r.run_id)} · ${esc(r.prompt_version || "—")}${r.frozen ? " · FREEZE.md" : ""}</dd>`).join("")}</div>
    <p class="dim small" style="margin:10px 0 0">The scoring is deterministic and the evaluator contains no LLM. The scored C1 records are frozen with SHA-256 hashes.</p></div>
  </div>`);
  two.appendChild(cards);
  view.appendChild(two);
}

/* ---------------------------------------------------------------- episodes grid */
let gridFilter = "all";
async function renderEpisodes() {
  const grid = await api.get("/api/grid?matrix=strong");
  view.innerHTML = "";
  const panel = node(`<section class="panel fade-in">
    <div class="panel-h"><div><h2>Episodes</h2><div class="muted small">Every agent faced the same hidden cultures. Click a cell to replay that agent's episode.</div></div>
      <div class="seg" id="flt"><button data-f="all">All</button><button data-f="BIOLOGICAL_PLATEAU">Biological plateau</button><button data-f="MEASUREMENT_ARTIFACT">Reader saturation</button></div></div>
    <div class="legend" style="margin-bottom:12px">${Object.values(OUTCOME).map((o) => `<span><i class="${o.cls}"></i>${o.label}</span>`).join("")}</div>
    <div style="overflow:auto"><table id="gt"></table></div></section>`);
  view.appendChild(panel);
  const draw = () => {
    panel.querySelectorAll("#flt button").forEach((b) => b.classList.toggle("on", b.dataset.f === gridFilter));
    const rows = grid.rows.filter((r) => gridFilter === "all" || r.condition === gridFilter);
    const cols = grid.columns;
    const t = panel.querySelector("#gt");
    const head = `<thead><tr><th>Episode</th><th>Seed</th><th>Hidden condition</th>${cols.map((c) => { const m = agentMeta(c.agent, c.model); return `<th style="text-align:center"><span style="color:${m.color}">${m.code}</span> ${esc(m.name)}</th>`; }).join("")}</tr></thead>`;
    const body = rows.map((r) => `<tr><td class="mono">${esc(r.episode_id)}</td><td class="mono dim">${esc(r.seed)}</td>
      <td><span class="tag" style="margin:0">${COND_LABEL[r.condition] || esc(r.condition)}</span></td>
      ${cols.map((c) => { const cell = r.cells[c.run_id]; if (!cell) return `<td style="text-align:center" class="dim">·</td>`;
        const o = outcome(cell, cell.status);
        return `<td style="text-align:center"><a class="cell ${OUTCOME[o].cls}" title="${OUTCOME[o].label}" href="#/episode/${encodeURIComponent(c.run_id)}/${encodeURIComponent(r.episode_id)}"></a></td>`; }).join("")}</tr>`).join("");
    const totals = cols.map((c) => { const cs = rows.map((r) => r.cells[c.run_id]).filter(Boolean);
      return `<td style="text-align:center" class="small"><b>${cs.filter((x) => x.justified).length}</b><span class="dim">/${cs.length}</span></td>`; }).join("");
    t.innerHTML = `${head}<tbody>${body}<tr><td colspan="3" class="muted small">Justified (M3)</td>${totals}</tr></tbody>`;
  };
  panel.querySelectorAll("#flt button").forEach((b) => b.addEventListener("click", () => { gridFilter = b.dataset.f; draw(); }));
  draw();
}

/* ---------------------------------------------------------------- episode detail */
function loopStepper(active) {
  const steps = [["Observe", "passive OD600 curve"], ["Ambiguity", "two worlds fit"], ["Experiment", "choose a control"], ["Evidence", "lab returns a reading"],
    ["Update", "revise belief"], ["Conclude", "diagnosis + p"], ["Score", "deterministic evaluator"]];
  return `<div class="loop">${steps.map(([b, s], i) => `<div class="s ${active.includes(i) ? "on" : ""}"><span class="n">${i + 1}</span><b>${b}</b>${s}</div>`).join("")}</div>`;
}

function timelineItems(rec) {
  const items = [];
  const evByTurn = new Map(rec.events.map((e) => [e.turn, e]));
  if (rec.llm_transcript) {
    for (const t of rec.llm_transcript) {
      if (t.kind !== "assistant") continue;
      const blocks = t.response?.content || [];
      for (const b of blocks) {
        if (b.type === "thinking" && b.thinking) items.push({ kind: "think", turn: t.turn, text: b.thinking });
        if (b.type === "text" && b.text) items.push({ kind: "text", turn: t.turn, text: b.text });
        if (b.type === "tool_use") items.push({ kind: "tool", turn: t.turn, tool: b.name, args: b.input, ev: evByTurn.get(t.turn) });
      }
    }
  } else {
    for (const e of rec.events) items.push({ kind: "tool", turn: e.turn, tool: e.tool, args: e.arguments, ev: e });
  }
  return items;
}

function renderTimeline(rec) {
  const items = timelineItems(rec);
  if (!items.length) return `<div class="empty">No agent actions recorded.</div>`;
  return `<div class="timeline">${items.map((it) => {
    if (it.kind === "think") return `<div class="tl think"><div class="h"><b>Turn ${it.turn}</b> · thinking</div><p class="small dim">${esc(it.text.slice(0, 600))}${it.text.length > 600 ? "…" : ""}</p></div>`;
    if (it.kind === "text") return `<div class="tl"><div class="h"><b>Turn ${it.turn}</b> · note</div><p>${esc(it.text)}</p></div>`;
    if (it.tool === "submit_diagnosis") {
      const a = it.args || {};
      return `<div class="tl diag"><div class="h"><b>Turn ${it.turn}</b> · submit_diagnosis</div><p><b>${DIAG_LABEL[a.diagnosis] || esc(a.diagnosis)}</b> · p = ${fmt(a.p_biomass_above_reading)} · estimate ${a.late_biomass_estimate_od ?? "—"}</p></div>`;
    }
    const a = it.args || {}, r = it.ev?.result;
    const res = it.ev?.ok === false ? `<span class="err">error: ${esc(it.ev.error)}</span>`
      : r && r.mean_reading != null ? `→ read <b>${fmt(r.mean_reading, 4)}</b> × ${r.dilution_factor} = <b style="color:var(--violet)">${fmt(r.mean_reading * r.dilution_factor, 3)}</b> · budget ${r.budget_remaining}`
      : r ? esc(JSON.stringify(r)) : "";
    const call = it.tool === "measure_od" ? `measure_od(t = ${a.time_h} h, 1:${a.dilution_factor ?? 1}, ×${a.replicates ?? 1})` : `${esc(it.tool)}(${esc(JSON.stringify(a))})`;
    return `<div class="tl"><div class="h"><b>Turn ${it.turn}</b> · tool call</div><pre>${call}</pre><p class="small" style="margin-top:4px">${res}</p></div>`;
  }).join("")}</div>`;
}

function verdictPanel(diag, scores, status, compact = false) {
  const o = outcome(scores, status);
  const color = { just: "var(--green)", unjust: "var(--amber)", wrong: "var(--red)", none: "var(--grey)" }[o];
  const p = diag?.p_biomass_above_reading;
  return `<div class="panel"><div class="panel-h"><h3>Verdict</h3><span class="small" style="color:${color};font-weight:650">${OUTCOME[o].label}</span></div>
    ${diag ? `<div class="verdict">${DIAG_LABEL[diag.diagnosis] || esc(diag.diagnosis)}</div>
    <div class="prob"><div class="pin" style="left:calc(${(p * 100).toFixed(1)}% - 2px)"></div></div>
    <div class="row small muted"><span>as read</span><span class="spacer"></span><span>P(above reading) = <b style="color:var(--text)">${fmt(p)}</b></span><span class="spacer"></span><span>above reading</span></div>
    <div class="kv small" style="margin-top:12px"><dt>Late biomass estimate</dt><dd>${diag.late_biomass_estimate_od ?? "—"}</dd><dt>Status</dt><dd>${esc(status)}</dd></div>
    ${!compact && diag.rationale ? `<div style="margin-top:14px"><h3 style="margin-bottom:6px">Lab notebook</h3><div class="notebook">${esc(diag.rationale)}</div></div>` : ""}` : `<div class="muted">No diagnosis submitted (${esc(status)}).</div>`}
    <div class="row" style="margin-top:14px">${scores ? [chip(scores.correct, "M1 correct"), chip(scores.diagnostic_control, "M2 control"), chip(scores.justified, "M3 justified"), chip(scores.reconstruction_adequate, "Q1 reconstruction")].join("") : ""}</div>
    ${scores ? `<div class="kv small" style="margin-top:10px"><dt>Brier</dt><dd>${fmt(scores.brier, 4)}</dd><dt>Cost</dt><dd>${scores.cost_units} / 6 units</dd></div>` : ""}</div>`;
}

function auditPanel(audit, events) {
  if (!audit || !audit.length) return `<div class="panel"><h3>Evaluator audit</h3><p class="muted small" style="margin:8px 0 0">No measurements, so there was nothing to audit. M2 and M3 cannot be earned without a diagnostic control.</p></div>`;
  const tick = (v) => (v ? `<span style="color:var(--green)">✓</span>` : `<span style="color:var(--red)">✗</span>`);
  return `<div class="panel"><div class="panel-h"><h3>Evaluator audit</h3><span class="dim small">per measurement, from frozen rules</span></div>
    <table class="small"><thead><tr><th>#</th><th>call</th><th title="in the late window">late</th><th title="dilution > 1">diluted</th><th title="in the frozen diagnostic action set">D_diag</th><th title="reading in useful region">useful</th><th title="before the diagnosis">before dx</th><th>control</th></tr></thead>
    <tbody>${audit.map((a) => { const ev = events[a.event_index]; const g = ev?.arguments || {};
      return `<tr><td class="dim">${a.event_index}</td><td class="mono" style="white-space:nowrap">${g.time_h ?? "?"}&nbsp;h&nbsp;·&nbsp;1:${g.dilution_factor ?? 1}</td><td>${tick(a.is_late)}</td><td>${tick(a.is_diluted)}</td><td>${tick(a.in_diagnostic_set)}</td><td>${tick(a.in_useful_region)}</td><td>${tick(a.before_diagnosis)}</td><td>${a.diagnostic_control ? '<span class="chip ok" style="height:20px">✓</span>' : '<span class="chip no" style="height:20px">✗</span>'}</td></tr>`; }).join("")}</tbody></table></div>`;
}

function revealPanel(ep, latent) {
  const K = ep.growth?.k_odeq, S = ep.assay?.s_odeq, x18 = latent?.length ? latent.at(-1)[1] : null;
  return `<div class="reveal-box fade-in"><h3 style="color:var(--amber);margin-bottom:8px">Hidden truth</h3>
    <div class="kv small"><dt>Condition</dt><dd><b>${COND_LABEL[ep.condition] || esc(ep.condition)}</b></dd>
    <dt>Carrying capacity K</dt><dd>${fmt(K, 3)} OD-eq</dd><dt>Reader ceiling S</dt><dd>${fmt(S, 3)} OD-eq</dd>
    <dt>K / S</dt><dd>${fmt(ep.k_ratio ?? (K && S ? K / S : null), 2)}</dd><dt>True biomass at 18 h</dt><dd>${fmt(x18, 3)}</dd>
    <dt>Growth r, ν</dt><dd>${fmt(ep.growth?.r_per_h, 3)} /h, ${fmt(ep.growth?.nu, 2)}</dd></div></div>`;
}

async function renderEpisode(runId, epId) {
  const [rs, rec] = await Promise.all([runs(), api.get(`/api/runs/${encodeURIComponent(runId)}/episodes/${encodeURIComponent(epId)}`)]);
  const run = rs.find((r) => r.run_id === runId) || {};
  const meta = agentMeta(rec.agent?.name || run.agent, rec.agent?.model || run.model);
  const d = rec.derived || {};
  const measurements = (d.measurements || []).map((m) => ({ ...m, label: `Turn ${m.turn}` }));
  let showTruth = false;
  view.innerHTML = "";
  const top = node(`<div class="row fade-in" style="margin-bottom:16px">
    <a href="#/episodes" class="btn ghost">← Episodes</a>
    <div><h2 class="mono" style="font-size:20px">${esc(epId)}</h2><div class="muted small"><span style="color:${meta.color}">●</span> ${meta.code} ${esc(meta.name)} · <span class="mono">${esc(runId)}</span> · seed ${esc(rec.episode.seed)}</div></div>
    <span class="spacer"></span><button class="btn" id="rv">Reveal hidden truth</button></div>`);
  view.appendChild(top);
  view.appendChild(node(`<div style="margin-bottom:18px">${loopStepper([0, 1, ...(measurements.length ? [2, 3, 4] : []), ...(rec.diagnosis ? [5] : []), 6])}</div>`));
  const body = node(`<div class="grid g-main">
    <div class="stack"><div class="panel"><div class="panel-h"><h2>Growth curve</h2><div class="legend">
      <span><i style="background:#3fd0e0"></i>undiluted readings</span><span><i style="background:#a78bfa"></i>agent dilution × factor</span><span id="lt" style="display:none"><i style="background:#f2b33d"></i>true biomass (hidden)</span></div></div>
      <div id="chart"></div></div>
      <div class="panel"><div class="panel-h"><h2>Agent loop</h2><span class="muted small">${meta.llm ? "LLM transcript (stored)" : "scripted agent: tool calls only"}</span></div>${renderTimeline(rec)}</div></div>
    <div class="stack">${verdictPanel(rec.diagnosis, rec.scores, rec.status)}<div id="rvp"></div>${auditPanel(rec.audit, rec.events)}</div></div>`);
  view.appendChild(body);
  const draw = () => {
    growthChart(body.querySelector("#chart"), { passive: rec.passive, measurements, latent: d.latent_curve, reading: d.reading_curve, ceiling: rec.episode.assay?.s_odeq, showTruth });
    body.querySelector("#lt").style.display = showTruth ? "" : "none";
    body.querySelector("#rvp").innerHTML = showTruth ? revealPanel(rec.episode, d.latent_curve) : "";
    top.querySelector("#rv").textContent = showTruth ? "Hide hidden truth" : "Reveal hidden truth";
  };
  top.querySelector("#rv").addEventListener("click", () => { showTruth = !showTruth; draw(); });
  draw();
}

/* ---------------------------------------------------------------- lab sandbox */
const lab = { session: null, obs: null, measurements: [], error: null, result: null, auto: {}, form: { time_h: 18, dilution_factor: 10, replicates: 1 }, dx: { diagnosis: null, p: 0.5, est: "", rationale: "" } };

async function labStart(body) {
  Object.assign(lab, { session: null, obs: null, measurements: [], error: null, result: null, auto: {}, dx: { diagnosis: null, p: 0.5, est: "", rationale: "" } });
  try {
    const r = await api.post("/api/sandbox", body);
    lab.session = r.session_id; lab.obs = r.observation; lab.budget = r.observation.budget_remaining; lab.preset = body.preset || null;
  } catch (e) { lab.error = e.message; }
  renderLab();
}

function renderLab() {
  view.innerHTML = "";
  const intro = node(`<section class="hero fade-in" style="padding-bottom:14px"><div>
    <div class="eyebrow">● Live · deterministic virtual lab · development seeds, never in metrics</div>
    <h1>You are the scientist.</h1>
    <p class="lead">A culture grew for 18 h. Its undiluted OD600 curve has flattened. Is the biomass <b>really</b> at that level, or has the reader saturated?
    You have 6 measurement units. Every request goes to the same lab and evaluator the agents faced.</p></div>
    <div class="panel"><h3>Start an episode</h3><div class="row" style="margin-top:12px">
      <button class="btn primary" data-start="random">New hidden culture</button>
      <button class="btn" data-start="demo-BP">Demo culture A</button>
      <button class="btn" data-start="demo-MA">Demo culture B</button></div>
      <p class="dim small" style="margin:12px 0 0">Demo cultures A and B are the matched pair from the pitch: their undiluted curves are identical.</p></div></section>`);
  intro.querySelectorAll("[data-start]").forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.start; labStart(k === "random" ? {} : { preset: k });
  }));
  view.appendChild(intro);
  if (lab.error && !lab.session) { view.appendChild(node(`<div class="panel err">${esc(lab.error)}</div>`)); return; }
  if (!lab.session) { view.appendChild(node(`<div class="panel empty">Start an episode to see its growth curve.</div>`)); return; }

  const done = !!lab.result;
  const rv = lab.result?.reveal;
  const grid = node(`<div class="grid g-main">
    <div class="stack"><div class="panel"><div class="panel-h"><h2>Your culture</h2><div class="legend"><span><i style="background:#3fd0e0"></i>undiluted readings</span><span><i style="background:#a78bfa"></i>your dilutions × factor</span>${done ? '<span><i style="background:#f2b33d"></i>true biomass</span>' : ""}</div></div>
      <div id="chart"></div>
      <p class="muted small" style="margin:8px 0 0">${done ? "The hidden truth is revealed." : "Two hidden worlds produce this curve. Which experiment tells them apart?"}</p></div>
      <div id="results"></div></div>
    <div class="stack" id="side"></div></div>`);
  view.appendChild(grid);
  growthChart(grid.querySelector("#chart"), {
    passive: lab.obs.passive_readings, measurements: lab.measurements.map((m, i) => ({ ...m, label: `Your measurement ${i + 1}` })),
    latent: rv?.latent_curve, reading: rv?.reading_curve, ceiling: rv?.assay?.s_odeq, showTruth: done,
  });
  const side = grid.querySelector("#side");

  if (!done) {
    const used = lab.obs.budget_total - lab.budget;
    const f = lab.form;
    const mp = node(`<div class="panel"><div class="panel-h"><h3>Measure a retained aliquot</h3><div class="budget" title="${lab.budget} of ${lab.obs.budget_total} units left">${Array.from({ length: lab.obs.budget_total }, (_, i) => `<i class="${i < used ? "used" : ""}"></i>`).join("")}</div></div>
      <label class="f">Time point: <b id="tv">${f.time_h} h</b></label><input type="range" min="0" max="18" step="1" value="${f.time_h}" id="t">
      <label class="f" style="margin-top:12px">Dilution</label><div class="seg" id="dil">${[1, 2, 5, 10, 20, 50, 100].map((v) => `<button data-v="${v}" class="${v === f.dilution_factor ? "on" : ""}">1:${v}</button>`).join("")}</div>
      <label class="f" style="margin-top:12px">Replicates (1 unit each)</label><div class="seg" id="rep">${[1, 2, 3].map((v) => `<button data-v="${v}" class="${v === f.replicates ? "on" : ""}">${v}</button>`).join("")}</div>
      <div class="row" style="margin-top:14px"><button class="btn primary" id="go" ${lab.budget < f.replicates ? "disabled" : ""}>Measure (${f.replicates} unit${f.replicates > 1 ? "s" : ""})</button><span class="muted small">${lab.budget} units left</span></div>
      ${lab.error ? `<p class="err small" style="margin:10px 0 0">${esc(lab.error)}</p>` : ""}</div>`);
    mp.querySelector("#t").addEventListener("input", (e) => { f.time_h = Number(e.target.value); mp.querySelector("#tv").textContent = `${f.time_h} h`; });
    mp.querySelectorAll("#dil button").forEach((b) => b.addEventListener("click", () => { f.dilution_factor = Number(b.dataset.v); renderLab(); }));
    mp.querySelectorAll("#rep button").forEach((b) => b.addEventListener("click", () => { f.replicates = Number(b.dataset.v); renderLab(); }));
    mp.querySelector("#go").addEventListener("click", async () => {
      lab.error = null;
      try {
        const r = await api.post(`/api/sandbox/${lab.session}/measure`, { time_h: f.time_h, dilution_factor: f.dilution_factor, replicates: f.replicates });
        if (r.ok) { lab.measurements.push({ ...r.result, replicates: f.replicates }); lab.budget = r.result.budget_remaining; }
        else lab.error = r.error;
      } catch (e) { lab.error = e.message; }
      renderLab();
    });
    side.appendChild(mp);

    const dx = lab.dx;
    const dp = node(`<div class="panel"><h3>Submit your diagnosis</h3>
      <div class="row" style="margin-top:12px"><button class="btn ${dx.diagnosis === "BIOMASS_AS_READ" ? "sel" : ""}" data-d="BIOMASS_AS_READ">Biomass as read</button><button class="btn ${dx.diagnosis === "BIOMASS_ABOVE_READING" ? "sel" : ""}" data-d="BIOMASS_ABOVE_READING">Biomass above reading</button></div>
      <label class="f" style="margin-top:14px">P(biomass above reading): <b id="pv">${dx.p.toFixed(2)}</b></label><input type="range" min="0" max="1" step="0.01" value="${dx.p}" id="p">
      <div class="grid g2" style="margin-top:12px;gap:12px"><div><label class="f">Late biomass estimate (OD, optional)</label><input type="number" min="0" step="0.01" id="est" value="${esc(dx.est)}"></div><div></div></div>
      <label class="f" style="margin-top:12px">Rationale</label><textarea id="rat" placeholder="What did your controls show?">${esc(dx.rationale)}</textarea>
      <div class="row" style="margin-top:12px"><button class="btn primary" id="sub" ${dx.diagnosis ? "" : "disabled"}>Submit and score</button><span class="dim small">The deterministic evaluator scores it, then the hidden world is revealed</span></div></div>`);
    dp.querySelectorAll("[data-d]").forEach((b) => b.addEventListener("click", () => { dx.diagnosis = b.dataset.d; renderLab(); }));
    dp.querySelector("#p").addEventListener("input", (e) => { dx.p = Number(e.target.value); dp.querySelector("#pv").textContent = dx.p.toFixed(2); });
    dp.querySelector("#est").addEventListener("input", (e) => { dx.est = e.target.value; });
    dp.querySelector("#rat").addEventListener("input", (e) => { dx.rationale = e.target.value; });
    dp.querySelector("#sub").addEventListener("click", async () => {
      const body = { diagnosis: dx.diagnosis, p_biomass_above_reading: dx.p, rationale: dx.rationale || "(none)" };
      if (dx.est !== "" && !Number.isNaN(Number(dx.est))) body.late_biomass_estimate_od = Number(dx.est);
      lab.error = null;
      try {
        const r = await api.post(`/api/sandbox/${lab.session}/diagnose`, body);
        if (r.ok === false) lab.error = r.error; else lab.result = r;
      } catch (e) { lab.error = e.message; }
      renderLab();
    });
    side.appendChild(dp);
    measurementsTable(grid.querySelector("#results"));
    return;
  }
  renderLabResult(grid, side);
}

function measurementsTable(target) {
  if (!lab.measurements.length) return;
  target.appendChild(node(`<div class="panel"><h3>Your measurements</h3><table class="small" style="margin-top:8px"><thead><tr><th>#</th><th>time</th><th>dilution</th><th>readings</th><th>mean</th><th>× factor</th></tr></thead><tbody>
        ${lab.measurements.map((m, i) => `<tr><td>${i + 1}</td><td>${m.time_h} h</td><td>1:${m.dilution_factor}</td><td class="mono">${m.readings.map((v) => v.toFixed(4)).join(", ")}</td><td class="mono">${m.mean_reading.toFixed(4)}</td><td class="mono" style="color:var(--violet)"><b>${(m.mean_reading * m.dilution_factor).toFixed(3)}</b></td></tr>`).join("")}</tbody></table></div>`));
}

function renderLabResult(grid, side) {
  measurementsTable(grid.querySelector("#results"));
  const r = lab.result;
  const o = outcome(r.scores, r.status);
  const headline = { just: "Correct and justified. That is good science.", unjust: "Correct, but not justified. You guessed.", wrong: "Wrong. The curve fooled you.", none: "No diagnosis." }[o];
  side.appendChild(node(`<div class="panel fade-in" style="border-color:${{ just: "rgba(62,207,142,.5)", unjust: "rgba(242,179,61,.5)", wrong: "rgba(240,100,108,.5)", none: "var(--line)" }[o]}"><h2>${headline}</h2>
    <p class="muted small" style="margin:6px 0 0">${o === "unjust" ? "M1 credits the right answer, but M3 needs a diagnostic dilution control before the diagnosis. This is exactly the right-answer, wrong-reason pattern MIRAGE catches." : o === "just" ? "You ran a control that separates the two worlds, and your answer followed from it." : "Compare your controls with GoodScientist's below."}</p></div>`));
  const vp = node(verdictPanel(r.diagnosis, r.scores, r.status, true)); side.appendChild(vp);
  side.appendChild(node(revealPanel({ ...r.reveal, k_ratio: r.reveal.k_ratio }, r.reveal.latent_curve)));
  side.appendChild(node(auditPanel(r.audit, r.events)));

  const cmp = node(`<div class="panel"><div class="panel-h"><h2>Same culture, other agents</h2><span class="muted small">deterministic scripted baselines, run live</span></div>
    <div class="row"><button class="btn" data-a="good_scientist">Run GoodScientist</button><button class="btn" data-a="passive_bayes">Run PassiveBayes</button><span class="spacer"></span><button class="btn primary" id="again">New culture</button></div>
    <div class="grid g2" style="margin-top:14px" id="autos"></div></div>`);
  cmp.querySelectorAll("[data-a]").forEach((b) => {
    const k = b.dataset.a;
    if (lab.auto[k] === "busy") { b.disabled = true; b.textContent = `Running ${agentMeta(k).name}…`; }
    b.addEventListener("click", async () => {
      if (lab.auto[k] === "busy") return;
      const session = lab.session;
      lab.auto[k] = "busy"; renderLab();
      let res;
      try { res = await api.post(`/api/sandbox/${session}/autoplay`, { agent: k }); }
      catch (e) { res = { error: e.message }; }
      if (lab.session !== session) return;
      lab.auto[k] = res; renderLab();
    });
  });
  cmp.querySelector("#again").addEventListener("click", () => labStart({}));
  const autos = cmp.querySelector("#autos");
  for (const [k, res] of Object.entries(lab.auto)) {
    if (res === "busy") { autos.appendChild(node(`<div class="panel muted small" style="padding:14px">Running ${esc(agentMeta(k).name)} on this culture…${k === "passive_bayes" ? " It integrates over the scenario prior, so this takes several seconds." : ""}</div>`)); continue; }
    if (res.error) { autos.appendChild(node(`<div class="err">${esc(res.error)}</div>`)); continue; }
    const meta = agentMeta(k);
    const ms = res.events.filter((e) => e.tool === "measure_od" && e.ok).map((e) => `${e.arguments.time_h} h · 1:${e.arguments.dilution_factor ?? 1} → ${(e.result.mean_reading * e.result.dilution_factor).toFixed(3)}`);
    const oo = outcome(res.scores, res.status);
    autos.appendChild(node(`<div class="panel" style="padding:14px"><div class="row"><b><span style="color:${meta.color}">●</span> ${meta.code} ${meta.name}</b><span class="spacer"></span><span class="small" style="font-weight:650">${OUTCOME[oo].label}</span></div>
      <div class="small muted" style="margin-top:6px">${ms.length ? ms.map(esc).join("<br>") : "No measurements: read the undiluted curve only."}</div>
      <div class="small" style="margin-top:6px">${DIAG_LABEL[res.diagnosis?.diagnosis] || "—"} · p = ${fmt(res.diagnosis?.p_biomass_above_reading)}</div>
      <div class="row" style="margin-top:8px">${chip(res.scores?.correct, "M1")}${chip(res.scores?.diagnostic_control, "M2")}${chip(res.scores?.justified, "M3")}</div></div>`));
  }
  grid.querySelector("#results").appendChild(cmp);
}

/* ---------------------------------------------------------------- method */
function renderMethod() {
  view.innerHTML = "";
  view.appendChild(node(`<div class="stack fade-in">
    <section><div class="eyebrow">● Method</div><h1>The scientific loop, scored deterministically.</h1>
      <p class="lead muted" style="max-width:820px">Each episode is one pass through the loop. The agent can repeat the experiment → evidence → update steps up to 12 turns, within a 6-unit measurement budget.</p></section>
    ${loopStepper([0, 1, 2, 3, 4, 5, 6])}
    <div class="grid g2">
      <div class="panel"><h3>World 1 · Biological plateau</h3><p>The culture genuinely reaches carrying capacity <b>K</b> below the reader's ceiling. A diluted read multiplied by its factor agrees with the undiluted reading.</p></div>
      <div class="panel"><h3>World 2 · Reader saturation</h3><p>The culture keeps going to a <b>K</b> several times above the reader's ceiling <b>S</b>. The undiluted readings flatten anyway, and only a dilution reveals the true biomass.</p></div>
    </div>
    <div class="grid g2">
      <div class="panel"><h3>Latent growth (Richards)</h3><div class="eq" style="margin-top:8px">dX/dt = r·X·[1 − (X/K)^ν]<br>X(t)^−ν = K^−ν + (X₀^−ν − K^−ν)·e^(−ν·r·t)</div></div>
      <div class="panel"><h3>Saturating assay</h3><div class="eq" style="margin-top:8px">f(x) = x · [1 + (x/S)^n]^(−1/n)</div><p class="muted small">Linear at low density, capped at S at high density. Blank-subtracted, with relative and absolute noise.</p></div>
    </div>
    <div class="panel"><h3>Metrics</h3><table style="margin-top:6px"><tbody>
      <tr><td><b>M1</b></td><td>Correct diagnosis (<code>BIOMASS_AS_READ</code> ↔ plateau, <code>BIOMASS_ABOVE_READING</code> ↔ saturation)</td></tr>
      <tr><td><b>M2</b></td><td>Made a diagnostic control: a late, diluted measurement in the frozen diagnostic action set, in the reader's useful region, before the diagnosis</td></tr>
      <tr><td><b>M3</b></td><td>Correct <i>and</i> justified by such a control. This is the headline: it catches right answers reached for the wrong reason</td></tr>
      <tr><td><b>Q1</b></td><td>Reconstruction adequacy (descriptive, not part of M3)</td></tr>
      <tr><td><b>Brier</b></td><td>Calibration of <code>p_biomass_above_reading</code></td></tr></tbody></table></div>
    <div class="grid g2">
      <div class="panel"><h3>Validity checks (Gate 0)</h3><p>Before any agent ran, Gate 0 checked that the passive curves are genuinely ambiguous and that a dilution control separates the worlds. The thresholds are frozen; Gate 0 is frozen.</p></div>
      <div class="panel"><h3>What this does not claim</h3><p class="muted">One controlled scenario and 30 sampled episodes per agent. The results show behaviour in MIRAGE-Bio, not general scientific ability. One known residual: in plateau cultures the reader under-reads by 2–4%. It is documented and was not used to rescore anything.</p></div>
    </div></div>`));
}

/* ---------------------------------------------------------------- router */
async function route() {
  const h = location.hash.replace(/^#\/?/, "");
  const [page, ...rest] = h.split("/");
  const key = page || "overview";
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === (key === "episode" ? "episodes" : key)));
  try {
    if (key === "overview") await renderOverview();
    else if (key === "episodes") await renderEpisodes();
    else if (key === "episode") await renderEpisode(decodeURIComponent(rest[0]), decodeURIComponent(rest[1]));
    else if (key === "lab") renderLab();
    else if (key === "method") renderMethod();
    else view.innerHTML = `<div class="empty">Not found.</div>`;
  } catch (e) {
    view.innerHTML = `<div class="panel err">Could not load: ${esc(e.message)}</div>`;
  }
  window.scrollTo(0, 0);
}

async function health() {
  const dot = document.getElementById("health-dot"), txt = document.getElementById("health-text");
  try { const h = await api.get("/api/health"); dot.className = "dot ok"; txt.textContent = `local API · v${h.version} · offline`; }
  catch { dot.className = "dot bad"; txt.textContent = "API unreachable"; }
}

window.addEventListener("hashchange", route);
health();
route();

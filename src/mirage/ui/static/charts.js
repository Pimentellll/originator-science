const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, parent) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
};

let tip;
function tooltip(html, ev) {
  if (!tip) { tip = document.createElement("div"); tip.className = "tooltip"; document.body.appendChild(tip); }
  if (html == null) { tip.style.display = "none"; return; }
  tip.innerHTML = html; tip.style.display = "block";
  tip.style.left = `${ev.clientX + 14}px`; tip.style.top = `${ev.clientY + 12}px`;
}

function niceMax(v) {
  if (!(v > 0)) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

/**
 * Growth chart: passive undiluted readings, agent dilution measurements
 * (raw and back-corrected x dilution), and optionally the hidden truth.
 * opts: {passive:[{time_h,mean_reading}], measurements:[{time_h,dilution_factor,mean_reading,replicates,label}],
 *        latent:[[t,x]], reading:[[t,y]], ceiling:number, showTruth:bool, height}
 */
export function growthChart(container, opts) {
  const W = 760, H = opts.height || 340, m = { l: 48, r: 18, t: 26, b: 34 };
  container.innerHTML = "";
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": "Growth curve" }, container);
  const defs = el("defs", {}, svg);
  const g1 = el("linearGradient", { id: "pg", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
  el("stop", { offset: "0%", "stop-color": "#3fd0e0", "stop-opacity": 0.22 }, g1);
  el("stop", { offset: "100%", "stop-color": "#3fd0e0", "stop-opacity": 0 }, g1);

  const meas = opts.measurements || [];
  const vals = [
    ...opts.passive.map((p) => p.mean_reading),
    ...meas.map((x) => x.mean_reading * x.dilution_factor),
  ];
  if (opts.showTruth && opts.latent) vals.push(...opts.latent.map((p) => p[1]));
  const yMax = niceMax(Math.max(...vals, 0.1) * 1.08);
  const x = (t) => m.l + (t / 18) * (W - m.l - m.r);
  const y = (v) => H - m.b - (v / yMax) * (H - m.t - m.b);

  const ax = el("g", { class: "axis" }, svg);
  for (let i = 0; i <= 5; i++) {
    const v = (yMax * i) / 5, yy = y(v);
    el("line", { x1: m.l, x2: W - m.r, y1: yy, y2: yy, class: "gridl" }, ax);
    const t = el("text", { x: m.l - 8, y: yy + 4, "text-anchor": "end" }, ax); t.textContent = v.toFixed(yMax < 2 ? 2 : 1);
  }
  for (let h = 0; h <= 18; h += 3) {
    const t = el("text", { x: x(h), y: H - m.b + 18, "text-anchor": "middle" }, ax); t.textContent = `${h} h`;
  }
  const yl = el("text", { x: m.l - 8, y: m.t - 12, "text-anchor": "end" }, ax); yl.textContent = "OD600";

  const lateX = x(12);
  el("rect", { x: lateX, y: m.t, width: x(18) - lateX, height: H - m.t - m.b, fill: "rgba(167,139,250,.05)" }, svg);
  const lw = el("text", { x: x(15), y: m.t + 12, "text-anchor": "middle", style: "fill:#7e6bbf;font-size:10.5px" }, svg);
  lw.textContent = "late window";

  if (opts.showTruth && opts.ceiling) {
    el("line", { x1: m.l, x2: W - m.r, y1: y(opts.ceiling), y2: y(opts.ceiling), stroke: "#f0646c", "stroke-dasharray": "2 4", "stroke-width": 1.2, opacity: 0.8 }, svg);
    const ct = el("text", { x: W - m.r - 4, y: y(opts.ceiling) - 5, "text-anchor": "end", style: "fill:#f0646c;font-size:10.5px" }, svg);
    ct.textContent = `reader ceiling S = ${opts.ceiling.toFixed(2)}`;
  }

  const path = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
  const pass = opts.passive.map((p) => [p.time_h, p.mean_reading]);
  if (pass.length) {
    el("path", { d: `${path(pass)}L${x(pass.at(-1)[0])},${y(0)}L${x(pass[0][0])},${y(0)}Z`, fill: "url(#pg)" }, svg);
    el("path", { d: path(pass), fill: "none", stroke: "#3fd0e0", "stroke-width": 2 }, svg);
  }
  if (opts.showTruth && opts.latent) {
    el("path", { d: path(opts.latent), fill: "none", stroke: "#f2b33d", "stroke-width": 2.2, "stroke-dasharray": "7 5", class: "fade-in" }, svg);
  }
  if (opts.showTruth && opts.reading) {
    el("path", { d: path(opts.reading), fill: "none", stroke: "#3fd0e0", "stroke-width": 1, opacity: 0.45, "stroke-dasharray": "1 3" }, svg);
  }

  const hover = (node, html) => {
    node.addEventListener("mousemove", (e) => tooltip(html, e));
    node.addEventListener("mouseleave", () => tooltip(null));
  };
  for (const p of opts.passive) {
    const c = el("circle", { cx: x(p.time_h), cy: y(p.mean_reading), r: 3.6, fill: "#0b1016", stroke: "#3fd0e0", "stroke-width": 1.8 }, svg);
    hover(c, `<b>${p.time_h} h</b> undiluted reading<br>${p.mean_reading.toFixed(4)}`);
  }
  meas.forEach((mm, i) => {
    const raw = mm.mean_reading, bc = raw * mm.dilution_factor, cx = x(mm.time_h) + ((i % 3) - 1) * 6;
    if (mm.dilution_factor > 1) {
      el("line", { x1: cx, x2: cx, y1: y(raw), y2: y(bc), stroke: "#a78bfa", "stroke-width": 1, "stroke-dasharray": "2 3", opacity: 0.7 }, svg);
      el("circle", { cx, cy: y(raw), r: 2.6, fill: "#a78bfa", opacity: 0.6 }, svg);
    }
    const s = 6.5;
    const d = el("path", { d: `M${cx},${y(bc) - s}L${cx + s},${y(bc)}L${cx},${y(bc) + s}L${cx - s},${y(bc)}Z`, fill: "#a78bfa", stroke: "#0b1016", "stroke-width": 1.5, class: "fade-in" }, svg);
    hover(d, `<b>${mm.label || `Measurement ${i + 1}`}</b> · ${mm.time_h} h<br>1:${mm.dilution_factor} dilution × ${mm.replicates || 1}<br>read ${raw.toFixed(4)} → ×${mm.dilution_factor} = <b>${bc.toFixed(3)}</b>`);
  });
  return svg;
}

/** Small horizontal bar with a Wilson interval whisker. */
export function rateBar(rate, ci, color) {
  const w = document.createElement("div");
  w.className = "bar";
  w.innerHTML = `<div class="fill" style="width:${(rate * 100).toFixed(1)}%;background:${color}"></div>` +
    (ci ? `<div class="ci" style="left:${(ci[0] * 100).toFixed(1)}%;width:${((ci[1] - ci[0]) * 100).toFixed(1)}%"></div>` : "");
  return w;
}

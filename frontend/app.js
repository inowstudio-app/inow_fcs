const $ = (s) => document.querySelector(s);
const form = $("#plotForm");
let LAST = null, LASTC = null, DXF = null, VIEW = "feasibility";

// ===== Units =====
let U = "m";
const FT = 3.280839895, SQFT = 10.76391042, INCH = 39.37007874;
const toM = (v, k) => (U === "ft" ? (k === "area" ? v / SQFT : v / FT) : v);
const convertVal = (v, k, a, b) => {
  const m = a === "ft" ? (k === "area" ? v / SQFT : v / FT) : v;
  return b === "ft" ? (k === "area" ? m * SQFT : m * FT) : m;
};
const roundU = (v, k) => (k === "area" ? Math.round(v) : Math.round(v * 100) / 100);
function feetInches(m) {
  const inches = m * INCH; let ft = Math.floor(inches / 12); let inch = Math.round(inches - ft * 12);
  if (inch === 12) { ft++; inch = 0; }
  return `${ft}′ ${inch}″`;
}
const fmtLen = (m) => (U === "m" ? `${Math.round(m * 100) / 100} m` : feetInches(m));
const fmtArea = (sqm) => (U === "m" ? `${fmt(Math.round(sqm * 10) / 10)} m²` : `${fmt(Math.round(sqm * SQFT))} sq.ft`);
const fmtByUnit = (v, unit) => (unit === "m" ? fmtLen(v) : unit === "m²" ? fmtArea(v) : `${v} ${unit || ""}`);

function updateUnitLabels() {
  document.querySelectorAll("[data-ulabel]").forEach(s => {
    const a = s.dataset.ulabel === "area";
    s.textContent = U === "m" ? (a ? "(m²)" : "(m)") : (a ? "(sq.ft)" : "(ft)");
  });
}
function setUnit(u) {
  if (u === U) return;
  const old = U; U = u;
  document.querySelectorAll("[data-u]").forEach(inp => {
    if (inp.value !== "" && !isNaN(+inp.value)) inp.value = roundU(convertVal(+inp.value, inp.dataset.u, old, U), inp.dataset.u);
  });
  updateUnitLabels();
  $("#uM").classList.toggle("uon", U === "m");
  $("#uF").classList.toggle("uon", U === "ft");
  if (LAST) renderFeasibility();
  if (LASTC) renderCompliance();
  if (DXF) renderDxf();
}
$("#uM").addEventListener("click", () => setUnit("m"));
$("#uF").addEventListener("click", () => setUnit("ft"));

// ===== health =====
fetch("/api/health").then(r => r.json()).then(h => {
  $("#ruleStatus").textContent = h.rules_loaded.join(" · ");
  if (h.auth) $("#logoutBtn").hidden = false;
}).catch(() => {});

// ===== logout / reset =====
$("#logoutBtn").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  location.reload();
});
$("#resetBtn").addEventListener("click", () => {
  ["survey_no", "village", "area_sqm", "side_n", "side_e", "side_s", "side_w"].forEach(n => form[n].value = "");
  form.polygon.value = ""; form.parking_area_class.value = ""; form.district.value = ""; form.plot_type.value = "individual";
  ["n", "e", "s", "w"].forEach(d => { $("#road_" + d).checked = false; $("#roadw_" + d).value = ""; $("#roadw_" + d).disabled = true; });
  AREA_MANUAL = false; $("#frontNote").textContent = "";
  $("#fmbExtract").hidden = true; $("#fmbPreviewWrap").hidden = true;
  $("#fmbStatus").textContent = "Optional — auto-extracts cadastral details & dimensions.";
  document.querySelectorAll(".need").forEach(e => e.classList.remove("need"));
});

// ===== tabs =====
document.querySelectorAll(".tab[data-view]").forEach(t => t.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
  t.classList.add("active");
  VIEW = t.dataset.view;
  const fullWidth = (VIEW === "projects" || VIEW === "dxf" || VIEW === "assistant");
  $("#proposalInputs").hidden = VIEW !== "compliance";
  $("#primaryBtn").style.display = fullWidth ? "none" : "";
  $("#primaryBtn").textContent = VIEW === "compliance" ? "Check compliance →" : "Analyse this plot →";
  $("#inputPanel").style.display = fullWidth ? "none" : "";
  document.querySelector("main").classList.toggle("full", fullWidth);
  showView();
  if (VIEW === "projects") loadProjects();
  if (VIEW === "assistant") checkAssistant();
}));
function showView() {
  ["feasibility", "compliance", "dxf", "assistant", "projects"].forEach(v => $("#view-" + v).hidden = v !== VIEW);
  $("#placeholder").hidden = (VIEW === "feasibility" && LAST) || (VIEW === "compliance" && LASTC) || fullWidthView();
}
function fullWidthView() { return ["projects", "dxf", "assistant"].includes(VIEW); }

// ===== DCR Assistant =====
let ASST_IMG = null, ASST_IMG_DATA = null;
let CONVO = newConvo();
function newConvo() { return { id: "c" + Date.now() + Math.random().toString(36).slice(2, 6), title: "", ts: Date.now(), messages: [] }; }
function loadChats() { try { return JSON.parse(localStorage.getItem("dcr_chats") || "[]"); } catch (e) { return []; } }
function saveChats(arr) {
  try { localStorage.setItem("dcr_chats", JSON.stringify(arr)); }
  catch (e) {  // quota exceeded -> drop stored images and retry
    const slim = arr.map(c => ({ ...c, messages: c.messages.map(m => ({ ...m, img: m.img ? null : undefined })) }));
    try { localStorage.setItem("dcr_chats", JSON.stringify(slim)); } catch (_) {}
  }
}
function convoPush(m) {
  CONVO.messages.push(m);
  if (!CONVO.title && m.role === "you") CONVO.title = (m.text || "sketch").slice(0, 40);
  CONVO.ts = Date.now();
  const all = loadChats().filter(c => c.id !== CONVO.id);
  all.unshift(CONVO);
  saveChats(all.slice(0, 25));
  refreshSavedList();
  $("#chatSaved").textContent = "saved ✓";
}
function refreshSavedList() {
  const sel = $("#savedChats"), cur = sel.value;
  const chats = loadChats();
  sel.innerHTML = `<option value="">Saved chats (${chats.length})…</option>` +
    chats.map(c => `<option value="${c.id}">${(c.title || "untitled").replace(/</g, "&lt;")} · ${new Date(c.ts).toLocaleDateString("en-GB")}</option>`).join("");
  sel.value = cur;
}
function loadConvo(id) {
  const c = loadChats().find(x => x.id === id); if (!c) return;
  CONVO = c;
  $("#asstThread").innerHTML = "";
  $("#asstCanvas").innerHTML = `<p class="placeholder">Diagrams and sketches appear here.</p>`;
  c.messages.forEach(m => {
    if (m.role === "you") { addBubble("you", m.text + (m.img ? "  [+ sketch]" : "")); if (m.img) showCanvas(`<img src="${m.img}" alt="sketch">`, "Your sketch"); }
    else renderAnswer(m.text, m.usage);
  });
  $("#chatSaved").textContent = "loaded";
}
$("#newChat").addEventListener("click", () => {
  CONVO = newConvo();
  $("#asstThread").innerHTML = "";
  $("#asstCanvas").innerHTML = `<p class="placeholder">Diagrams the assistant draws, and sketches you attach, appear here — large.</p>`;
  $("#savedChats").value = ""; $("#chatSaved").textContent = "";
});
$("#savedChats").addEventListener("change", (e) => { if (e.target.value) loadConvo(e.target.value); });
refreshSavedList();
async function checkAssistant() {
  try {
    const s = await (await fetch("/api/assistant/status")).json();
    const n = $("#asstNotice");
    if (s.configured) { n.hidden = true; }
    else { n.hidden = false; n.textContent = "⚠ Assistant not switched on — add ANTHROPIC_API_KEY in the server environment to enable answers."; }
  } catch (e) {}
}
$("#asstImg").addEventListener("change", (e) => {
  ASST_IMG = e.target.files[0] || null;
  ASST_IMG_DATA = null;
  $("#asstImgName").textContent = ASST_IMG ? "Attached: " + ASST_IMG.name : "";
  if (ASST_IMG) { const fr = new FileReader(); fr.onload = () => { ASST_IMG_DATA = fr.result; }; fr.readAsDataURL(ASST_IMG); }
});
$("#asstSend").addEventListener("click", async () => {
  const q = $("#asstQ").value.trim();
  if (!q && !ASST_IMG) return;
  addBubble("you", q + (ASST_IMG ? "  [+ sketch]" : ""));
  if (ASST_IMG_DATA) showCanvas(`<img src="${ASST_IMG_DATA}" alt="sketch">`, "Your sketch");
  convoPush({ role: "you", text: q, img: ASST_IMG_DATA || null });
  $("#asstQ").value = "";
  const thinking = addBubble("dcr", "…thinking…");
  const fd = new FormData();
  fd.append("question", q);
  if (ASST_IMG) fd.append("image", ASST_IMG);
  try {
    const r = await fetch("/api/assistant", { method: "POST", body: fd });
    const d = await r.json().catch(() => ({}));
    const ans = d.answer || d.detail || ("Error " + r.status + " — no response from server.");
    thinking.remove();
    renderAnswer(ans, d.usage);
    convoPush({ role: "dcr", text: ans, usage: d.usage });
  } catch (err) { thinking.remove(); addBubble("dcr", "Error: " + err.message); }
  ASST_IMG = null; ASST_IMG_DATA = null; $("#asstImg").value = ""; $("#asstImgName").textContent = "";
});
function addBubble(who, text) {
  const div = document.createElement("div");
  div.className = "bubble " + who;
  div.textContent = text;
  $("#asstThread").appendChild(div);
  div.scrollIntoView({ block: "end" });
  return div;
}
function renderAnswer(text, usage) {
  const div = document.createElement("div");
  div.className = "bubble dcr";
  // pull verdict
  let html = "";
  const vm = text.match(/VERDICT:\s*(Allowed|Not allowed|Conditional)/i);
  if (vm) {
    const v = vm[1].toLowerCase();
    const cls = v === "allowed" ? "ok" : v === "not allowed" ? "fail" : "cond";
    html += `<div class="verdict ${cls}" style="font-size:15px;padding:6px 12px;margin:0 0 8px">${vm[1].toUpperCase()}</div>`;
    text = text.replace(vm[0], "");
  }
  // extract an svg block to render inline
  let svg = "";
  text = text.replace(/```svg\s*([\s\S]*?)```/i, (_, s) => { svg = s.replace(/<script[\s\S]*?<\/script>/gi, ""); return ""; });
  html += "<div>" + escapeHtml(text.trim()).replace(/\n/g, "<br>") + "</div>";
  if (svg) html += `<div class="hint" style="margin-top:6px">▶ diagram shown on the right →</div>`;
  if (usage && usage.input) html += `<div class="hint" style="margin-top:6px">~${usage.input} in / ${usage.output} out tokens</div>`;
  div.innerHTML = html;
  $("#asstThread").appendChild(div);
  div.scrollIntoView({ block: "end" });
  if (svg) showCanvas(svg, "Diagram");
}
function showCanvas(inner, label) {
  $("#asstCanvas").innerHTML = (label ? `<div class="canvas-label">${label}</div>` : "") + inner;
}
function escapeHtml(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

// ===== district dropdown =====
const TN_DISTRICTS = ["Ariyalur","Chengalpattu","Chennai","Coimbatore","Cuddalore","Dharmapuri","Dindigul","Erode","Kallakurichi","Kancheepuram","Kanniyakumari","Karur","Krishnagiri","Madurai","Mayiladuthurai","Nagapattinam","Namakkal","Nilgiris","Perambalur","Pudukkottai","Ramanathapuram","Ranipet","Salem","Sivaganga","Tenkasi","Thanjavur","Theni","Thoothukudi","Tiruchirappalli","Tirunelveli","Tirupathur","Tiruppur","Tiruvallur","Tiruvannamalai","Tiruvarur","Vellore","Viluppuram","Virudhunagar"];
(function () { const s = $("#districtSel"); TN_DISTRICTS.forEach(d => { const o = document.createElement("option"); o.value = d; o.textContent = d; s.appendChild(o); }); })();

// ===== road sides + auto-area =====
let AREA_MANUAL = false;
const SIDE_NAMES = { N: "North", E: "East", S: "South", W: "West" };
["n", "e", "s", "w"].forEach(d => {
  $("#road_" + d).addEventListener("change", (e) => {
    $("#roadw_" + d).disabled = !e.target.checked;
    if (!e.target.checked) $("#roadw_" + d).value = "";
    updateFrontNote();
  });
  $("#roadw_" + d).addEventListener("input", updateFrontNote);
});
form.district.addEventListener("change", () => {
  if (form.district.value === "Chennai" && !form.parking_area_class.value) form.parking_area_class.value = "cmda";
});
["side_n", "side_e", "side_s", "side_w"].forEach(n => form[n].addEventListener("input", recalcArea));
form.area_sqm.addEventListener("input", () => { AREA_MANUAL = form.area_sqm.value !== ""; });

function collectRoads() {           // -> { N: widthMetres, ... }
  const r = {};
  ["n", "e", "s", "w"].forEach(d => {
    if ($("#road_" + d).checked) { const v = +$("#roadw_" + d).value; if (v > 0) r[d.toUpperCase()] = toM(v, "len"); }
  });
  return r;
}
function updateFrontNote() {
  const roads = collectRoads(), ks = Object.keys(roads);
  if (!ks.length) { $("#frontNote").textContent = ""; return; }
  let front = null, w = 0;
  for (const [s, ww] of Object.entries(roads)) if (ww > w) { w = ww; front = s; }
  $("#frontNote").textContent = `Front = ${SIDE_NAMES[front]} side (widest road, ${fmtLen(w)}).`
    + (ks.length > 1 ? " Other road sides take side/rear setback." : "");
}
function avgPos(a, b) { const v = [a, b].filter(x => x > 0); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : 0; }
function recalcArea() {
  if (AREA_MANUAL) return;
  const wd = avgPos(+form.side_n.value, +form.side_s.value), dp = avgPos(+form.side_e.value, +form.side_w.value);
  if (wd > 0 && dp > 0) form.area_sqm.value = roundU(wd * dp, "area");  // sides & area share the display unit
}

// ===== gather plot inputs (convert to metres) =====
function plotBody() {
  const g = n => (form[n] ? form[n].value : "");
  const b = { plot_type: form.plot_type.value, parking_area_class: form.parking_area_class.value };
  if (g("survey_no")) b.survey_no = g("survey_no");
  if (g("village")) b.village = g("village");
  if (g("district")) b.district = g("district");
  const N = toM(+g("side_n"), "len"), E = toM(+g("side_e"), "len"), S = toM(+g("side_s"), "len"), Wd = toM(+g("side_w"), "len");
  const width = avgPos(N, S), depth = avgPos(E, Wd);    // metres
  let area = toM(+g("area_sqm"), "area");
  if (!area && width && depth) area = width * depth;
  b.area_sqm = area || width * depth || 0;
  b.width_m = width || Math.sqrt(area || 0);
  b.depth_m = depth || Math.sqrt(area || 0);
  const roads = collectRoads();
  b.road_sides = roads;
  let widest = 0, front = null;
  for (const [s, w] of Object.entries(roads)) if (w > widest) { widest = w; front = s; }
  b.abutting_road_width_m = widest;
  b.front_edge_idx = ({ S: 0, E: 1, N: 2, W: 3 })[front] ?? 0;
  const poly = form.polygon.value.trim();
  if (poly) {
    const pts = poly.split(/\n+/).map(l => l.split(",").map(Number)).filter(p => p.length === 2 && !p.some(isNaN));
    if (pts.length >= 3) b.polygon = pts;
  }
  return b;
}
function setLen(name, metres) { form[name].value = roundU(convertVal(metres, "len", "m", U), "len"); }

function validPlot(b) {
  if (!(b.area_sqm > 0 && b.width_m > 0 && b.depth_m > 0)) {
    alert("Please enter the plot sides (or the area).");
    return false;
  }
  if (!(b.abutting_road_width_m > 0)) {
    alert("Please tick at least one abutting road and enter its width.");
    return false;
  }
  return true;
}

// ===== primary action =====
$("#primaryBtn").addEventListener("click", () => {
  if (VIEW === "compliance") return runCompliance();
  return runFeasibility();
});
async function runFeasibility() {
  const body = plotBody(); if (!validPlot(body)) return;
  const r = await fetch("/api/scenarios", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) return alert("Error: " + await r.text());
  LAST = await r.json(); LAST.inputs = plotBody();
  renderFeasibility();
}
async function runCompliance() {
  const pb = plotBody(); if (!validPlot(pb)) return;
  const body = {
    plot: pb, height_m: toM(+$("#p_height").value, "len"), dwellings: +$("#p_dwellings").value,
    front_setback_m: toM(+$("#p_front").value, "len"), side_setback_m: toM(+$("#p_side").value, "len"),
    rear_setback_m: toM(+$("#p_rear").value, "len"), built_up_area_sqm: toM(+$("#p_bua").value, "area"),
    footprint_area_sqm: toM(+$("#p_fp").value, "area"), car_parking_provided: +$("#p_cars").value,
  };
  const r = await fetch("/api/compliance", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) return alert("Error: " + await r.text());
  LASTC = await r.json(); LASTC.inputs = body.plot;
  renderCompliance();
}

// ===== FMB upload =====
const FMB_LABELS = { survey_no: "Survey No", village: "Village", area_sqm: "Area", width_m: "Frontage",
  depth_m: "Depth", abutting_road_width: "Abutting road width", local_body: "Planning authority" };

$("#fmbFile").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (!f) return;
  $("#fmbStatus").textContent = "Reading FMB…";
  const fd = new FormData(); fd.append("file", f);
  try {
    const r = await fetch("/api/fmb/parse", { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const d = await r.json();
    $("#fmbPreview").src = "data:image/png;base64," + d.preview_png_b64;
    $("#fmbPreviewWrap").hidden = false;
    const p = d.parsed, det = d.detected || {};
    if (det.survey_no) form.survey_no.value = p.survey_no;
    if (det.village) form.village.value = p.village;
    if (p.district && TN_DISTRICTS.includes(p.district)) form.district.value = p.district;
    if (p.dimensions && p.dimensions.length >= 4) {
      const ds = [...p.dimensions].sort((a, b) => a - b);
      setLen("side_n", ds[0]); setLen("side_s", ds[1]); setLen("side_e", ds[2]); setLen("side_w", ds[3]);
    } else if (det.width_m && det.depth_m) {
      setLen("side_n", p.width_m); setLen("side_s", p.width_m); setLen("side_e", p.depth_m); setLen("side_w", p.depth_m);
    }
    if (det.area_sqm) { form.area_sqm.value = roundU(convertVal(p.area_sqm, "area", "m", U), "area"); AREA_MANUAL = true; }

    const filledKeys = ["survey_no", "village", "area_sqm"].filter(k => det[k]);
    const filled = filledKeys.map(k => FMB_LABELS[k]);
    if (p.dimensions && p.dimensions.length) filled.push("Plot sides");
    const miss = (d.missing || []).filter(k => !["width_m", "depth_m"].includes(k)).map(k => FMB_LABELS[k] || k);
    const dimsTxt = (p.dimensions && p.dimensions.length)
      ? `<div class="ex-dim">Detected edge lengths: ${p.dimensions.join(", ")} m → filled into the 4 sides (adjust which side is which if needed).</div>` : "";
    $("#fmbExtract").hidden = false;
    $("#fmbExtract").innerHTML =
      `<div class="ex-ok">✓ Auto-filled: ${filled.join(", ") || "none"}</div>` +
      (miss.length ? `<div class="ex-miss">⚠ Not on the FMB — please enter: ${miss.join(", ")}</div>` : "") + dimsTxt;
    $("#fmbStatus").textContent = d.method === "ocr" ? "Read via OCR." : d.method === "text" ? "Read from PDF text." : "Could not read text — enter manually.";
  } catch (err) { $("#fmbStatus").textContent = "Could not read FMB: " + err.message; }
});

// ===== DXF import =====
$("#dxfFile").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (!f) return;
  $("#dxfStatus").textContent = "Reading DXF…";
  const fd = new FormData(); fd.append("file", f);
  try {
    const r = await fetch("/api/dxf/parse", { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    DXF = await r.json();
    DXF.plotSel = DXF.suggested_plot_idx;
    DXF.buildSel = DXF.suggested_building_idx;
    $("#dxfStatus").textContent = `${DXF.polyline_count} polyline(s) · units: ${DXF.units.name}. ${DXF.note}`;
    $("#dxfResult").hidden = false;
    renderDxf();
  } catch (err) { $("#dxfStatus").textContent = "Could not read DXF: " + err.message; }
});
function renderDxf() {
  if (!DXF) return;
  $("#dxfTable").innerHTML = `<tr><th>#</th><th>Layer</th><th>Role</th><th>Area</th><th>Size</th><th>Plot</th><th>Bldg</th></tr>` +
    DXF.polylines.map((p, i) => `<tr>
      <td>${i}</td><td>${p.layer}</td><td>${p.role !== "other" ? `<b>${p.role}</b>` : "—"}</td>
      <td>${p.closed ? fmtArea(p.area_sqm) : "open"}</td>
      <td>${fmtLen(p.bbox.w)} × ${fmtLen(p.bbox.d)}</td>
      <td>${p.closed ? `<input type="radio" name="plotsel" ${i === DXF.plotSel ? "checked" : ""} onclick="dxfPick('plot',${i})">` : ""}</td>
      <td>${p.closed ? `<input type="radio" name="buildsel" ${i === DXF.buildSel ? "checked" : ""} onclick="dxfPick('build',${i})">` : ""}</td></tr>`).join("");
  drawDxfOverlay();
}
function dxfPick(which, i) { if (which === "plot") DXF.plotSel = i; else DXF.buildSel = i; drawDxfOverlay(); }
function drawDxfOverlay() {
  const svg = $("#dxfOverlay");
  const all = DXF.polylines.flatMap(p => p.points);
  if (!all.length) { svg.innerHTML = ""; return; }
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const VB = 420, pad = 24, sc = Math.min((VB - 2 * pad) / (maxX - minX || 1), (VB - 2 * pad) / (maxY - minY || 1));
  const ox = (VB - (maxX - minX) * sc) / 2, oy = (VB - (maxY - minY) * sc) / 2;
  const map = ([x, y]) => `${ox + (x - minX) * sc},${oy + (maxY - y) * sc}`;
  svg.innerHTML = DXF.polylines.map((p, i) => {
    const col = i === DXF.plotSel ? "#1f9d5c" : i === DXF.buildSel ? "#1668b3" : "#aab4c0";
    const fill = i === DXF.plotSel ? "rgba(31,157,92,.12)" : i === DXF.buildSel ? "rgba(22,104,179,.12)" : "none";
    const pts = p.points.map(map).join(" ");
    return p.closed ? `<polygon points="${pts}" fill="${fill}" stroke="${col}" stroke-width="2"/>`
                    : `<polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1" stroke-dasharray="4"/>`;
  }).join("");
}
$("#dxfScrutiny").addEventListener("click", async () => {
  if (!DXF || DXF.plotSel == null || DXF.buildSel == null) return alert("Select both a plot boundary and a building footprint.");
  const body = {
    plot_coords: DXF.polylines[DXF.plotSel].points,
    building_coords: DXF.polylines[DXF.buildSel].points,
    front_edge_idx: 0,
    road_width_m: toM(+$("#sc_road").value, "len"), height_m: toM(+$("#sc_height").value, "len"),
    floors: +$("#sc_floors").value, dwellings: +$("#sc_dwellings").value,
    use: $("#sc_use").value, area_class: $("#sc_class").value,
  };
  const r = await fetch("/api/scrutiny", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) return alert("Error: " + await r.text());
  window.SCR = await r.json();
  renderScrutiny();
});
function renderScrutiny() {
  const s = window.SCR; if (!s) return;
  $("#scrutinyReport").hidden = false;
  const ad = s.auto_derived, sb = ad.setbacks_m;
  const v = s.verdict === "COMPLIANT";
  $("#scMeta").textContent = `Auto-derived from drawing · ${new Date().toLocaleDateString("en-GB")}`;
  $("#scVerdict").innerHTML = `<div class="verdict ${v ? "ok" : "fail"}">${v ? "✓ COMPLIANT" : "✕ NON-COMPLIANT — " + s.deviation_count + " deviation(s)"}</div>
    <p class="hint">${s.rule} · ${s.building_class.replace("_", "-")}</p>`;
  $("#scAuto").innerHTML = [
    kpi(fmtArea(ad.plot_area_sqm), "Plot area", ""), kpi(fmtArea(ad.footprint_sqm), "Footprint", `${ad.coverage_pct}% cover`),
    kpi(fmtArea(ad.built_up_sqm), "Built-up", `${ad.floors} floors`),
    kpi(fmtLen(sb.front), "Front (auto)", ""), kpi(fmtLen(sb.side), "Side (auto)", ""), kpi(fmtLen(sb.rear), "Rear (auto)", ""),
  ].join("");
  $("#scTable").innerHTML = `<tr><th>Item</th><th>Required</th><th>Provided</th><th>Status</th></tr>` +
    s.checks.map(c => `<tr class="${c.status === "FAIL" ? "rfail" : c.status === "PASS" ? "rpass" : ""}">
      <td>${c.item}</td><td>${c.required != null ? fmtByUnit(c.required, c.unit || "m") : "—"}</td>
      <td>${c.proposed != null ? fmtByUnit(c.proposed, c.unit || "m") : "—"}</td><td><b>${c.status.replace("_", " ")}</b></td></tr>`).join("");
  $("#scWarn").innerHTML = (s.warnings || []).map(w => `<div class="flag">⚠ ${w}</div>`).join("");
  drawScrutinyOverlay(s.geometry);
}
function drawScrutinyOverlay(geo) {
  const svg = $("#dxfOverlay");
  const all = geo.plot.concat(geo.building);
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const VB = 420, pad = 30, sc = Math.min((VB - 2 * pad) / (maxX - minX || 1), (VB - 2 * pad) / (maxY - minY || 1));
  const ox = (VB - (maxX - minX) * sc) / 2, oy = (VB - (maxY - minY) * sc) / 2;
  const map = ([x, y]) => `${ox + (x - minX) * sc},${oy + (maxY - y) * sc}`;
  svg.innerHTML = `<polygon points="${geo.plot.map(map).join(" ")}" fill="rgba(31,157,92,.10)" stroke="#1f9d5c" stroke-width="2"/>
    <polygon points="${geo.building.map(map).join(" ")}" fill="rgba(22,104,179,.18)" stroke="#1668b3" stroke-width="1.5"/>
    <text x="${VB / 2}" y="${oy - 8}" text-anchor="middle" font-size="11" fill="#1668b3" font-weight="600">building inside plot</text>`;
}

$("#dxfUse").addEventListener("click", () => {
  if (!DXF || DXF.plotSel == null) return alert("Select which polyline is the plot boundary.");
  const plot = DXF.polylines[DXF.plotSel];
  form.polygon.value = plot.points.map(p => `${p[0]},${p[1]}`).join("\n");   // metres
  form.area_sqm.value = roundU(convertVal(plot.area_sqm, "area", "m", U), "area");
  form.width_m.value = roundU(convertVal(plot.bbox.w, "len", "m", U), "len");
  form.depth_m.value = roundU(convertVal(plot.bbox.d, "len", "m", U), "len");
  document.querySelector('.tab[data-view="feasibility"]').click();
  alert("Plot geometry loaded from DXF (" + fmtArea(plot.area_sqm) + "). Click 'Analyse this plot'.");
});

$("#printBtn").addEventListener("click", () => window.print());

async function downloadPdf(kind) {
  const map = { feasibility: LAST, compliance: LASTC, scrutiny: window.SCR };
  const result = map[kind];
  if (!result) return alert("Run the analysis first.");
  const meta = kind === "feasibility" ? $("#rhMeta").textContent : kind === "compliance" ? $("#cMeta").textContent : $("#scMeta").textContent;
  const r = await fetch("/api/report/pdf", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind, meta, result }) });
  if (!r.ok) return alert("PDF error: " + await r.text());
  const blob = await r.blob(), url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = `DCR_${kind}_report.pdf`; a.click();
  URL.revokeObjectURL(url);
}

// ===== save =====
document.querySelectorAll("[data-save]").forEach(btn => btn.addEventListener("click", async () => {
  const src = btn.dataset.save === "feasibility" ? LAST : LASTC;
  if (!src) return alert("Run an analysis first.");
  const client = prompt("Client name?") || "";
  const i = src.inputs;
  const body = { client, title: `${i.survey_no || "plot"} — ${btn.dataset.save}`, kind: btn.dataset.save, inputs: i, result: src };
  const r = await fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (r.ok) { const d = await r.json(); alert("Saved as project #" + d.id); }
}));

// ===== render feasibility =====
function renderFeasibility() {
  showView();
  const i = LAST.inputs;
  const today = new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  $("#rhMeta").textContent = `Survey ${i.survey_no || "—"}, ${i.village || "—"} · Plot ${fmtArea(i.area_sqm)} · Road ${fmtLen(i.abutting_road_width_m)} · ${today}`;
  $("#scenarioCards").innerHTML = LAST.scenarios.map((s, idx) => {
    const rec = s.scenario === LAST.recommended;
    if (!s.feasible) return `<div class="scard no"><div class="sc-name">${s.scenario}</div><div class="sc-no">✕ ${s.reason}</div></div>`;
    const u = s.est_dwelling_units != null ? `${s.est_dwelling_units} units` : "—";
    return `<div class="scard ${rec ? "rec" : ""}" data-idx="${idx}">${rec ? '<div class="rec-badge">★ Recommended</div>' : ""}
      <div class="sc-name">${s.scenario}</div><div class="sc-big">${fmtArea(s.max_built_up_sqm)}</div>
      <div class="sc-sub">max built-up · FSI ${s.fsi}</div>
      <div class="sc-row"><span>${s.floors} fl</span><span>${u}</span><span>${s.parking.car_spaces} cars</span></div></div>`;
  }).join("");
  let sn = document.getElementById("siteNotes");
  if (!sn) { sn = document.createElement("div"); sn.id = "siteNotes"; $("#scenarioCards").after(sn); }
  sn.innerHTML = (LAST.site_notes || []).map(n => `<div class="advis">ⓘ ${n}</div>`).join("");
  document.querySelectorAll(".scard[data-idx]").forEach(el => el.addEventListener("click", () => selectScenario(+el.dataset.idx)));
  const ri = LAST.scenarios.findIndex(s => s.scenario === LAST.recommended);
  selectScenario(ri >= 0 ? ri : LAST.scenarios.findIndex(s => s.feasible));
  $("#pendingList").innerHTML = (LAST.pending || []).map(p => `<li>${p}</li>`).join("");
  const am = LAST.amendments;
  if (am) $("#amendBlock").innerHTML = `<h4>Amendments layered</h4>
    <div class="hint">Reviewed through <b>${am.reviewed_through}</b> · ${am.reviewed}/${am.total} GOs reviewed
    ${am.numeric_overrides_applied.length ? "· applied: " + am.numeric_overrides_applied.join(", ") : ""}
    ${am.pending_review.length ? `· <span style="color:var(--amber)">${am.pending_review.length} older scanned GO(s) pending OCR</span>` : ""}</div>`;
}
function selectScenario(idx) {
  const s = LAST.scenarios[idx]; if (!s || !s.feasible) return;
  document.querySelectorAll(".scard").forEach(el => el.classList.toggle("sel", +el.dataset.idx === idx));
  $("#detailTitle").textContent = "Selected — " + s.scenario;
  const sb = s.setbacks_m, pk = s.parking, pr = s.premium_fsi, osr = s.osr;
  $("#kpis").innerHTML = [
    kpi(fmtArea(s.max_built_up_sqm), "Max built-up", `FSI ${s.fsi} · ${s.floors} floors`),
    kpi(s.est_dwelling_units != null ? s.est_dwelling_units : "—", "Est. units", ""),
    kpi(fmtArea(s.footprint_sqm), "Footprint", `${s.coverage_pct}% coverage`),
    kpi(fmtLen(sb.front), "Front SB", ""), kpi(fmtLen(sb.side), "Side SB", sb.side_applies), kpi(fmtLen(sb.rear), "Rear SB", ""),
  ].join("");
  $("#upsideBlock").innerHTML = `<h4>Upside &amp; obligations</h4>
    <div class="row2"><span>Premium FSI (Rule 49)</span><b>${pr.premium_pct ? "+" + pr.premium_pct + "% = " + fmtArea(pr.upside_sqm) : "—"}</b></div>
    <div class="row2"><span>OSR reqd (Rule 41)</span><b>${osr.required_sqm ? fmtArea(osr.required_sqm) + " (" + osr.pct + "%)" : "Nil"}</b></div>`;
  $("#parkingBlock").innerHTML = `<h4>Parking (Annexure IV)</h4><div class="pk"><b>${pk.car_spaces}</b> car · <b>${pk.two_wheeler_spaces}</b> TW</div><div class="hint">${pk.basis}. ${pk.note}</div>`;
  $("#flags").innerHTML = (s.flags || []).map(f => `<div class="flag">⚠ ${f}</div>`).join("")
    + (s.advisories || []).map(a => `<div class="advis">ⓘ ${a}</div>`).join("");
  $("#citation").textContent = s.rule;
  drawOverlay(s.geometry);
}

// ===== render compliance =====
function renderCompliance() {
  showView();
  const i = LASTC.inputs;
  $("#cMeta").textContent = `Survey ${i.survey_no || "—"} · Plot ${fmtArea(i.area_sqm)} · Road ${fmtLen(i.abutting_road_width_m)}`;
  if (!LASTC.buildable) {
    $("#verdict").innerHTML = `<div class="verdict fail">Not buildable: ${LASTC.reason}</div>`;
    $("#checksTable").innerHTML = ""; return;
  }
  const v = LASTC.verdict === "COMPLIANT";
  $("#verdict").innerHTML = `<div class="verdict ${v ? "ok" : "fail"}">${v ? "✓ COMPLIANT" : "✕ NON-COMPLIANT — " + LASTC.deviation_count + " deviation(s)"}</div>
    <p class="hint">${LASTC.rule} · ${LASTC.building_class.replace("_", "-")}</p>`;
  $("#checksTable").innerHTML = `<tr><th>Item</th><th>Required</th><th>Proposed</th><th>Status</th></tr>` +
    LASTC.checks.map(c => `<tr class="${c.status === "FAIL" ? "rfail" : c.status === "PASS" ? "rpass" : ""}">
      <td>${c.item}</td><td>${c.required != null ? fmtByUnit(c.required, c.unit || "m") : "—"}</td>
      <td>${c.proposed != null ? fmtByUnit(c.proposed, c.unit || "m") : "—"}</td>
      <td><b>${c.status.replace("_", " ")}</b></td></tr>`).join("");
}

// ===== projects =====
async function loadProjects() {
  const rows = await (await fetch("/api/projects")).json();
  $("#projectsTable").innerHTML = `<tr><th>#</th><th>Client</th><th>Title</th><th>Survey</th><th>Kind</th><th>Date</th><th></th></tr>` +
    (rows.length ? rows.map(r => `<tr><td>${r.id}</td><td>${r.client || "—"}</td><td>${r.title}</td><td>${r.survey_no || "—"}</td>
      <td>${r.kind}</td><td>${(r.created_at || "").slice(0, 10)}</td>
      <td><button class="mini" onclick="openProject(${r.id})">open</button> <button class="mini del" onclick="delProject(${r.id})">del</button></td></tr>`).join("")
      : `<tr><td colspan="7" class="hint" style="padding:14px">No saved projects yet. Run a study and click ★ Save.</td></tr>`);
}
async function openProject(id) {
  const p = await (await fetch("/api/projects/" + id)).json();
  const i = p.inputs;
  if (i.area_sqm != null) { form.area_sqm.value = roundU(convertVal(i.area_sqm, "area", "m", U), "area"); AREA_MANUAL = true; }
  if (i.width_m) { setLen("side_n", i.width_m); setLen("side_s", i.width_m); }
  if (i.depth_m) { setLen("side_e", i.depth_m); setLen("side_w", i.depth_m); }
  ["survey_no", "village"].forEach(k => { if (i[k] != null) form[k].value = i[k]; });
  if (i.district) form.district.value = i.district;
  if (i.plot_type) form.plot_type.value = i.plot_type;
  if (i.road_sides) Object.entries(i.road_sides).forEach(([s, w]) => {
    const d = s.toLowerCase(); if ($("#road_" + d)) { $("#road_" + d).checked = true; $("#roadw_" + d).disabled = false; $("#roadw_" + d).value = roundU(convertVal(w, "len", "m", U), "len"); }
  });
  updateFrontNote();
  if (p.kind === "feasibility") { LAST = p.result; LAST.inputs = i; document.querySelector('.tab[data-view="feasibility"]').click(); renderFeasibility(); }
  else { LASTC = p.result; LASTC.inputs = i; document.querySelector('.tab[data-view="compliance"]').click(); renderCompliance(); }
}
async function delProject(id) { if (confirm("Delete project #" + id + "?")) { await fetch("/api/projects/" + id, { method: "DELETE" }); loadProjects(); } }

// ===== helpers =====
function fmt(n) { return Number(n).toLocaleString("en-IN"); }
function kpi(v, l, s) { return `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div><div class="s">${s}</div></div>`; }

function drawOverlay(geo) {
  const svg = $("#overlay");
  if (!geo || !geo.plot) { svg.innerHTML = ""; return; }
  const all = geo.plot.concat(geo.buildable && geo.buildable.length ? geo.buildable : []);
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const VB = 420, VBH = 460, pad = 50;
  const sc = Math.min((VB - 2 * pad) / (maxX - minX || 1), (VBH - 2 * pad) / (maxY - minY || 1));
  const ox = (VB - (maxX - minX) * sc) / 2, oy = (VBH - (maxY - minY) * sc) / 2;
  const map = ([x, y]) => `${ox + (x - minX) * sc},${oy + (y - minY) * sc}`;
  const plotPts = geo.plot.map(map).join(" ");
  const buildPts = (geo.buildable || []).map(map).join(" ");
  const fe = geo.plot[geo.front_edge_idx], fe2 = geo.plot[(geo.front_edge_idx + 1) % geo.plot.length];
  const fmx = ox + ((fe[0] + fe2[0]) / 2 - minX) * sc, fmy = oy + ((fe[1] + fe2[1]) / 2 - minY) * sc;
  svg.innerHTML = `
    <polygon points="${plotPts}" fill="rgba(217,77,58,.10)" stroke="#334155" stroke-width="2"/>
    ${buildPts ? `<polygon points="${buildPts}" fill="rgba(31,157,92,.18)" stroke="#1f9d5c" stroke-width="1.5"/>` : ""}
    <text x="${fmx}" y="${fmy - 8}" text-anchor="middle" font-size="11" fill="#1668b3" font-weight="600">▲ FRONT / ROAD</text>
    ${buildPts ? `<text x="${VB / 2}" y="${oy + (maxY - minY) * sc / 2}" text-anchor="middle" font-size="11" fill="#1f9d5c">buildable</text>` : ""}`;
}

updateUnitLabels();

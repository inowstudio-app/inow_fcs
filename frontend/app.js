const $ = (s) => document.querySelector(s);
const form = $("#plotForm");
let LAST = null, LASTC = null, DXF = null, VIEW = "feasibility";

// ===== Units (default = Feet/inches) =====
let U = "ft";
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
// dual=true appends the other unit in a smaller bracketed span (for innerHTML panels);
// pass dual=false for plain text (SVG / textContent).
function fmtLen(m, dual = true) {
  const meters = `${Math.round(m * 100) / 100} m`, fi = feetInches(m);
  const main = U === "m" ? meters : fi, alt = U === "m" ? fi : meters;
  return dual ? `${main} <span class="alt">(${alt})</span>` : main;
}
function fmtArea(sqm, dual = true) {
  const m2 = `${fmt(Math.round(sqm * 10) / 10)} m²`, sf = `${fmt(Math.round(sqm * SQFT))} sq.ft`;
  const main = U === "m" ? m2 : sf, alt = U === "m" ? sf : m2;
  return dual ? `${main} <span class="alt">(${alt})</span>` : main;
}
const fmtByUnit = (v, unit, dual = true) => (unit === "m" ? fmtLen(v, dual) : unit === "m²" ? fmtArea(v, dual) : `${v} ${unit || ""}`);

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
$("#uM").classList.toggle("uon", U === "m");
$("#uF").classList.toggle("uon", U === "ft");

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
  ["ne", "nw", "se", "sw"].forEach(c => { $("#splay_" + c).checked = false; $("#splayd_" + c).value = ""; $("#splayd_" + c).disabled = true; });
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
  const fullWidth = (VIEW === "projects" || VIEW === "dxf" || VIEW === "assistant" || VIEW === "neufert");
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
  ["feasibility", "compliance", "dxf", "assistant", "neufert", "projects"].forEach(v => $("#view-" + v).hidden = v !== VIEW);
  $("#placeholder").hidden = (VIEW === "feasibility" && LAST) || (VIEW === "compliance" && LASTC) || fullWidthView();
}
function fullWidthView() { return ["projects", "dxf", "assistant", "neufert"].includes(VIEW); }

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
    else renderAnswer(m.text, m.usage, m.svg);
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
    renderAnswer(ans, d.usage, d.svg);
    convoPush({ role: "dcr", text: ans, usage: d.usage, svg: d.svg });
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
function renderAnswer(text, usage, svgArg) {
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
  // prefer the server-cleaned svg; fall back to an inline ```svg fence (older saved chats)
  let svg = svgArg || "";
  if (!svg) {
    text = text.replace(/```svg\s*([\s\S]*?)```/i, (_, s) => { svg = s.replace(/<script[\s\S]*?<\/script>/gi, ""); return ""; });
  }
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
["ne", "nw", "se", "sw"].forEach(c => {
  $("#splay_" + c).addEventListener("change", (e) => { $("#splayd_" + c).disabled = !e.target.checked; if (!e.target.checked) $("#splayd_" + c).value = ""; recalcArea(); });
  $("#splayd_" + c).addEventListener("input", recalcArea);
});
function collectSplays() {  // -> { NE: lengthMetres, ... }
  const s = {};
  ["ne", "nw", "se", "sw"].forEach(c => { if ($("#splay_" + c).checked) { const v = +$("#splayd_" + c).value; if (v > 0) s[c.toUpperCase()] = toM(v, "len"); } });
  return s;
}
const splayAreaM = () => Object.values(collectSplays()).reduce((a, L) => a + 0.5 * L * L, 0);

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
  $("#frontNote").textContent = `Front = ${SIDE_NAMES[front]} side (widest road, ${fmtLen(w, false)}).`
    + (ks.length > 1 ? " Other road sides take side/rear setback." : "");
}
function avgPos(a, b) { const v = [a, b].filter(x => x > 0); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : 0; }
function recalcArea() {
  if (AREA_MANUAL) return;
  const wd = avgPos(+form.side_n.value, +form.side_s.value), dp = avgPos(+form.side_e.value, +form.side_w.value);
  if (wd > 0 && dp > 0) {
    const splayDisp = splayAreaM() * (U === "ft" ? SQFT : 1);   // splay triangles, in display units²
    form.area_sqm.value = roundU(Math.max(0, wd * dp - splayDisp), "area");
  }
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
  b.sides = { N, E, S, W: Wd };       // metres, for the oriented diagram
  b.front_side = front;               // compass letter of the front (widest road)
  b.splays = collectSplays();         // {NE:metres,...} corner cuts (diagram + area)
  const polyText = form.polygon.value.trim();
  let polygon = null;
  if (polyText) {
    const pts = polyText.split(/\n+/).map(l => l.split(",").map(Number)).filter(p => p.length === 2 && !p.some(isNaN));
    if (pts.length >= 3) polygon = pts;
  } else {
    polygon = reconstructQuad(N, E, S, Wd);   // build the real quadrilateral from 4 sides
  }
  if (polygon && polygon.length >= 3) b.polygon = polygon;
  return b;
}
function setLen(name, metres) { form[name].value = roundU(convertVal(metres, "len", "m", U), "len"); }

// Reconstruct the plot quadrilateral (metres) from the 4 side lengths.
// Anchor: NORTH edge horizontal at the top (y=0); East edge perpendicular (drops down);
// then solve the SW corner so South & West lengths close exactly — matches a surveyor sketch.
// Vertices order [SW, SE, NE, NW] => engine edges South=0/East=1/North=2/West=3.
function reconstructQuad(N, E, S, Wd) {
  if (!(N > 0 && E > 0 && S > 0 && Wd > 0)) return null;
  const NW = [0, 0], NE = [N, 0], SE = [N, -E];          // North across top, East straight down
  const K = (S * S - Wd * Wd - N * N - E * E) / 2;       // solve SW from |SW-NW|=W and |SW-SE|=S
  const a = E * E + N * N, b = 2 * K * N, c = K * K - Wd * Wd * E * E;
  const disc = b * b - 4 * a * c;
  if (disc >= 0) {
    const sq = Math.sqrt(disc);
    const cand = [(-b + sq) / (2 * a), (-b - sq) / (2 * a)]
      .map(x => [x, (K + N * x) / E]).filter(p => p[1] < 0.01);   // corner must sit below North
    if (cand.length) { cand.sort((p, q) => p[1] - q[1]); return [cand[0], SE, NE, NW]; }
  }
  return [[0, -Wd], SE, NE, NW];   // fallback (still North-anchored)
}

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
  const body = { client, title: `${i.survey_no || "plot"} — ${btn.dataset.save}`, kind: btn.dataset.save, inputs: i, result: src, survey_no: i.survey_no || "", village: i.village || "" };
  const d = lsAddProject(body);
  alert("Saved as project #" + d.id + " (stored in this browser — survives refresh & logout).");
}));

// ===== render feasibility =====
function renderFeasibility() {
  showView();
  const i = LAST.inputs;
  const today = new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  $("#rhMeta").textContent = `Survey ${i.survey_no || "—"}, ${i.village || "—"} · Plot ${fmtArea(i.area_sqm, false)} · Road ${fmtLen(i.abutting_road_width_m, false)} · ${today}`;
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
  // default to Single residence (frequent use case); fall back to recommended, then any feasible
  let di = LAST.scenarios.findIndex(s => s.feasible && /single residence/i.test(s.scenario));
  if (di < 0) di = LAST.scenarios.findIndex(s => s.scenario === LAST.recommended && s.feasible);
  if (di < 0) di = LAST.scenarios.findIndex(s => s.feasible);
  if (di >= 0) selectScenario(di);
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
  const plotArea = LAST.inputs.area_sqm || 0;
  const gfArea = s.footprint_sqm || 0;                 // ground-floor buildable (after setbacks)
  const setbackArea = Math.max(0, plotArea - gfArea);  // open/setback area
  $("#upsideBlock").innerHTML = `<h4>Ground floor (after setbacks)</h4>
    <div class="row2"><span>GF buildable footprint</span><b>${fmtArea(gfArea)}</b></div>
    <div class="row2"><span>Setback / open area</span><b>${fmtArea(setbackArea)}</b></div>
    <div class="row2"><span>Ground coverage</span><b>${s.coverage_pct}%</b></div>
    <h4 style="margin-top:12px">Upside &amp; obligations</h4>
    <div class="row2"><span>Premium FSI (Rule 49)</span><b>${pr.premium_pct ? "+" + pr.premium_pct + "% = " + fmtArea(pr.upside_sqm) : "—"}</b></div>
    <div class="row2"><span>OSR reqd (Rule 41)</span><b>${osr.required_sqm ? fmtArea(osr.required_sqm) + " (" + osr.pct + "%)" : "Nil"}</b></div>`;
  $("#parkingBlock").innerHTML = `<h4>Parking (Annexure IV)</h4><div class="pk"><b>${pk.car_spaces}</b> car · <b>${pk.two_wheeler_spaces}</b> TW</div><div class="hint">${pk.basis}. ${pk.note}</div>`;
  $("#flags").innerHTML = (s.flags || []).map(f => `<div class="flag">⚠ ${f}</div>`).join("")
    + (s.advisories || []).map(a => `<div class="advis">ⓘ ${a}</div>`).join("");
  $("#citation").textContent = s.rule;
  drawOverlay(s, LAST.inputs);
}

// ===== render compliance =====
function renderCompliance() {
  showView();
  const i = LASTC.inputs;
  $("#cMeta").textContent = `Survey ${i.survey_no || "—"} · Plot ${fmtArea(i.area_sqm, false)} · Road ${fmtLen(i.abutting_road_width_m, false)}`;
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

// ===== projects (browser localStorage — survives refresh / logout / redeploy) =====
function lsLoadProjects() { try { return JSON.parse(localStorage.getItem("dcr_projects") || "[]"); } catch (e) { return []; } }
function lsSaveProjects(arr) { try { localStorage.setItem("dcr_projects", JSON.stringify(arr)); return true; } catch (e) { return false; } }
function lsAddProject(p) {
  const all = lsLoadProjects();
  p.id = Date.now();
  p.created_at = new Date().toISOString().slice(0, 19);
  all.unshift(p);
  // if over quota, drop oldest until it fits
  while (all.length > 1 && !lsSaveProjects(all)) all.pop();
  lsSaveProjects(all);
  return p;
}
async function loadProjects() {
  const rows = lsLoadProjects();
  $("#projectsTable").innerHTML = `<tr><th>#</th><th>Client</th><th>Title</th><th>Survey</th><th>Kind</th><th>Date</th><th></th></tr>` +
    (rows.length ? rows.map(r => `<tr><td>${r.id}</td><td>${r.client || "—"}</td><td>${r.title}</td><td>${r.survey_no || "—"}</td>
      <td>${r.kind}</td><td>${(r.created_at || "").slice(0, 10)}</td>
      <td><button class="mini" onclick="openProject(${r.id})">open</button> <button class="mini del" onclick="delProject(${r.id})">del</button></td></tr>`).join("")
      : `<tr><td colspan="7" class="hint" style="padding:14px">No saved projects yet. Run a study and click ★ Save.</td></tr>`);
}
async function openProject(id) {
  const p = lsLoadProjects().find(x => x.id === id);
  if (!p) return alert("Project not found in this browser.");
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
async function delProject(id) { if (confirm("Delete project #" + id + "?")) { lsSaveProjects(lsLoadProjects().filter(x => x.id !== id)); loadProjects(); } }

// ===== helpers =====
function fmt(n) { return Number(n).toLocaleString("en-IN"); }
function kpi(v, l, s) { return `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div><div class="s">${s}</div></div>`; }

// North-up diagram drawn from the ACTUAL plot polygon (proportional to the side lengths),
// with edge-relative side lengths, setbacks, splay chamfers, all road markers, N arrow.
const norm2 = v => { const L = Math.hypot(v[0], v[1]) || 1; return [v[0] / L, v[1] / L]; };
const centroidM = poly => { let x = 0, y = 0; poly.forEach(p => { x += p[0]; y += p[1]; }); return [x / poly.length, y / poly.length]; };
const edgeLenM = (poly, i) => { const a = poly[i], b = poly[(i + 1) % poly.length]; return Math.hypot(b[0] - a[0], b[1] - a[1]); };
function chamfer(poly, byIdx) {
  const n = poly.length, out = [];
  for (let i = 0; i < n; i++) {
    const L = byIdx[i] || 0, V = poly[i], P = poly[(i - 1 + n) % n], Nx = poly[(i + 1) % n];
    if (L <= 0) { out.push(V); continue; }
    const np = norm2([P[0] - V[0], P[1] - V[1]]), nn = norm2([Nx[0] - V[0], Nx[1] - V[1]]);
    out.push([V[0] + np[0] * L, V[1] + np[1] * L]); out.push([V[0] + nn[0] * L, V[1] + nn[1] * L]);
  }
  return out;
}
function drawOverlay(s, inputs) {
  const svg = $("#overlay"); const geo = s.geometry;
  if (!geo || !geo.plot || geo.plot.length < 3) { svg.innerHTML = ""; return; }
  const sp = inputs.splays || {}, cornerIdx = { SW: 0, SE: 1, NE: 2, NW: 3 };
  const splayByIdx = {}; Object.keys(sp).forEach(c => { if (cornerIdx[c] != null && sp[c] > 0) splayByIdx[cornerIdx[c]] = sp[c]; });
  const plotM = chamfer(geo.plot, splayByIdx), bldM = geo.buildable || [];
  const all = plotM.concat(bldM), xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const W = (maxX - minX) || 1, D = (maxY - minY) || 1, VB = 460, VBH = 480, pad = 90;
  const sc = Math.min((VB - 2 * pad) / W, (VBH - 2 * pad) / D);
  const ox = (VB - W * sc) / 2, oy = (VBH - D * sc) / 2;
  const mp = ([x, y]) => [ox + (x - minX) * sc, oy + (maxY - y) * sc];   // North (max y) at top
  const T = (x, y, t, fill = "#66758a", fw = "400", fs = 10) => `<text x="${x}" y="${y}" text-anchor="middle" font-size="${fs}" fill="${fill}" font-weight="${fw}">${t}</text>`;
  const plotS = plotM.map(mp), bldS = bldM.map(mp), cenS = mp(centroidM(geo.plot)), n = geo.plot.length;
  const sb = s.setbacks_m, sd = inputs.sides || {}, fEdge = inputs.front_edge_idx ?? 0, rEdge = (fEdge + 2) % n;
  const sideByEdge = [sd.S, sd.E, sd.N, sd.W], roadEdge = { N: 2, E: 1, S: 0, W: 3 };
  const emid = i => { const a = mp(geo.plot[i]), b = mp(geo.plot[(i + 1) % n]); return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]; };
  const outv = (m, d) => { let dx = m[0] - cenS[0], dy = m[1] - cenS[1]; const L = Math.hypot(dx, dy) || 1; return [m[0] + dx / L * d, m[1] + dy / L * d]; };

  let o = `<polygon points="${plotS.map(p => p.join(",")).join(" ")}" fill="rgba(217,77,58,.10)" stroke="#334155" stroke-width="2"/>`;
  if (bldS.length >= 3) o += `<polygon points="${bldS.map(p => p.join(",")).join(" ")}" fill="rgba(31,157,92,.18)" stroke="#1f9d5c" stroke-width="1.5"/>`;
  for (let i = 0; i < n; i++) {
    const m = emid(i);
    const sl = (n === 4 && sideByEdge[i]) ? sideByEdge[i] : edgeLenM(geo.plot, i);
    const op = outv(m, 22); o += T(op[0], op[1] + 3, fmtLen(sl, false));
    const sv = i === fEdge ? sb.front : i === rEdge ? sb.rear : sb.side;
    const ip = outv(m, -15); o += T(ip[0], ip[1] + 3, fmtLen(sv, false), "#1f9d5c");
  }
  if (bldS.length) {
    const bxs = bldS.map(p => p[0]), bys = bldS.map(p => p[1]);
    const cx = (Math.min(...bxs) + Math.max(...bxs)) / 2, cy = (Math.min(...bys) + Math.max(...bys)) / 2;
    o += T(cx, cy - 6, "buildable", "#1f9d5c", "600");
    o += T(cx, cy + 9, fmtLen((Math.max(...bxs) - Math.min(...bxs)) / sc, false), "#1f9d5c");
    o += T(cx, cy + 23, "× " + fmtLen((Math.max(...bys) - Math.min(...bys)) / sc, false), "#1f9d5c");
  }
  Object.keys(sp).forEach(c => { const i = cornerIdx[c]; if (sp[c] > 0 && i != null && geo.plot[i]) { const v = outv(mp(geo.plot[i]), -2); o += T(v[0], v[1], "splay " + fmtLen(sp[c], false), "#b97400", "600"); } });
  const roads = inputs.road_sides || {};
  Object.keys(roads).forEach(side => { const i = roadEdge[side]; if (i == null || i >= n) return; const m = outv(emid(i), 42), isF = i === fEdge; o += T(m[0], m[1], (isF ? "▲ FRONT/ROAD " : "ROAD ") + fmtLen(roads[side], false), "#1668b3", isF ? 700 : 600, isF ? 11 : 10); });
  o += `<g transform="translate(${VB - 22},26)"><line x1="0" y1="12" x2="0" y2="-8" stroke="#334155" stroke-width="1.5"/><path d="M0,-13 L-5,-4 L5,-4 Z" fill="#334155"/><text x="0" y="-16" text-anchor="middle" font-size="11" fill="#334155" font-weight="700">N</text></g>`;
  svg.setAttribute("viewBox", `0 0 ${VB} ${VBH}`);
  svg.innerHTML = o;
}

updateUnitLabels();

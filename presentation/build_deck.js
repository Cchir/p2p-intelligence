// Builds presentation/Procure-to-Pay-Intelligence-Stratum.pptx from deck_data.json (exported from the
// project's outputs) and the dashboard screenshots.  Run:  node build_deck.js
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const lu = require("react-icons/lu");
const { applyTheme } = require("./apply_theme.js");

const D = JSON.parse(fs.readFileSync(path.join(__dirname, "deck_data.json"), "utf8"));
const M = D.metrics;
const FIG = path.join(__dirname, "..", "reports", "figures");
const OUT = path.join(__dirname, "Procure-to-Pay-Intelligence-Stratum.pptx");

// Stratum brand (stratumdata.org). Dark deck: lt1/lt2 carry text, dk1/dk2 carry background/surfaces.
const HEX = {
  ink: "0B0E13", surface: "141A24", hi: "EEF2F8", text: "C5CDDA",
  cobalt: "8AA0FF", amber: "F2B65C", teal: "58D6C2", muted: "8C97A8", deep: "5A6CF0", line: "242E3D",
};
const THEME = {
  name: "Stratum Dark", headFontFace: "Arial", bodyFontFace: "Calibri",
  colors: {
    dk1: HEX.ink, lt1: HEX.hi, dk2: HEX.surface, lt2: HEX.text,
    accent1: HEX.cobalt, accent2: HEX.amber, accent3: HEX.teal, accent4: HEX.muted,
    accent5: HEX.deep, accent6: HEX.line, hlink: HEX.cobalt, folHlink: HEX.teal,
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.author = "Stratum";
pres.company = "Stratum";
pres.title = "Procure-to-Pay Intelligence: a Stratum case study";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;
const INK = C.text1, SURFACE = C.text2, HI = C.background1, TEXT = C.background2;
const COBALT = C.accent1, AMBER = C.accent2, TEAL = C.accent3, MUTED = C.accent4, LINE = C.accent6;
const HEAD = "+mj-lt";
const W = 13.333, MX = 0.6;

// ---------------------------------------------------------------- layouts
pres.defineSlideMaster({
  title: "Title",
  background: { color: INK },
  objects: [
    { placeholder: { options: { name: "eyebrow", type: "body", x: MX + 0.4, y: 1.55, w: 9, h: 0.4, fontSize: 13, bold: true, color: COBALT, charSpacing: 4, margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 2.1, w: 11.5, h: 2.2, fontSize: 54, bold: true, color: HI, margin: 0, valign: "top", align: "left" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: MX, y: 4.45, w: 9.8, h: 1.2, fontSize: 20, color: TEXT, margin: 0, valign: "top" }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "Content",
  background: { color: INK },
  objects: [
    { text: { text: "stratum  ·  Procure-to-Pay Intelligence case study", options: { x: MX, y: 6.98, w: 6, h: 0.3, fontSize: 10, color: MUTED, margin: 0 } } },
    { placeholder: { options: { name: "eyebrow", type: "body", x: MX + 0.3, y: 0.42, w: 10, h: 0.3, fontSize: 12, bold: true, color: COBALT, charSpacing: 4, margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 0.8, w: W - 2 * MX, h: 0.8, fontSize: 34, bold: true, color: HI, margin: 0, valign: "top", align: "left" }, text: "" } },
  ],
  slideNumber: { x: W - MX - 0.6, y: 6.98, w: 0.6, h: 0.3, fontSize: 10, color: MUTED, align: "right" },
});

// ---------------------------------------------------------------- helpers
const iconCache = {};
async function icon(name, hex) {
  const key = name + hex;
  if (!iconCache[key]) {
    const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(lu[name], { color: "#" + hex, size: 256, strokeWidth: 1.75 }));
    iconCache[key] = "image/png;base64," + (await sharp(Buffer.from(svg)).resize(256, 256).png().toBuffer()).toString("base64");
  }
  return iconCache[key];
}
function brandDot(slide, x, y) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 0.14, h: 0.14, rectRadius: 0.03, fill: { color: COBALT }, line: { type: "none" }, objectName: "brand mark" });
}
function card(slide, x, y, w, h, name) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: SURFACE }, line: { color: LINE, width: 0.75 }, objectName: name });
}
async function iconTile(slide, name, x, y, colorHex, size = 0.62) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: size, h: size, rectRadius: 0.1, fill: { color: INK }, line: { color: LINE, width: 0.75 }, objectName: "icon tile" });
  const pad = size * 0.22;
  slide.addImage({ data: await icon(name, colorHex), x: x + pad, y: y + pad, w: size - 2 * pad, h: size - 2 * pad, altText: name.replace("Lu", "") + " icon" });
}
function text(slide, t, opts) {
  slide.addText(t, { isTextBox: true, margin: 0, color: TEXT, fontSize: 15, valign: "top", ...opts });
}
function content(eyebrow, title, section) {
  const s = pres.addSlide({ masterName: "Content", sectionTitle: section });
  brandDot(s, MX, 0.5);
  s.addText(eyebrow.toUpperCase(), { placeholder: "eyebrow" });
  s.addText(title, { placeholder: "title" });
  return s;
}
const axis = () => ({
  catAxisLabelColor: HEX.muted, valAxisLabelColor: HEX.muted, catAxisLabelFontSize: 11, valAxisLabelFontSize: 11,
  catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisLineShow: false, valAxisLineShow: false,
  valGridLine: { color: HEX.line, size: 0.75 }, catGridLine: { style: "none" },
  legendFontFace: "+mn-lt", legendFontSize: 12, legendColor: HEX.text, dataLabelFontFace: "+mn-lt",
  titleFontFace: "+mn-lt", titleColor: HEX.hi, titleFontSize: 14,
});
const stat = (s, n, l, x, y, w, col, size = 40) => {
  text(s, n, { x, y, w, h: 0.75, fontSize: size, bold: true, color: col, fontFace: HEAD, valign: "middle" });
  text(s, l, { x, y: y + 0.8, w, h: 0.7, fontSize: 13.5, color: TEXT });
};
const m1 = (v) => "€" + (v / 1e6).toFixed(1) + "M";

async function build() {
  const eff = M.causal.effects[0];
  const comp = M.compliance.overall;
  const cash = Object.fromEntries(M.survival.cash_forecast.map((r) => [r.horizon_days, r.expected_cash_out_eur]));
  const bt = M.survival.backtest;
  const err = (a, b) => Math.abs(a / b - 1);
  const modelErr = bt.reduce((t, r) => t + err(r.forecast_eur, r.actual_eur), 0) / bt.length;
  const naiveErr = bt.reduce((t, r) => t + err(r.naive_last_period_eur, r.actual_eur), 0) / bt.length;
  const seq = M.sequence.results[0];
  const conf = M.conformal.results;
  const best = M.alerts.best;
  const am = M.alerts.metrics;
  const km = M.survival.median_days.three_way_before_gr;
  const sod = M.compliance.rules.find((r) => r.rule === "r06_segregation_of_duties").n_items;

  // 1. Title
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "Title", sectionTitle: "Introduction" });
  brandDot(s, MX, 1.68);
  s.addText("STRATUM  ·  CASE STUDY", { placeholder: "eyebrow" });
  s.addText("Procure-to-Pay Intelligence", { placeholder: "title" });
  s.addText("What 1.6 million ERP events reveal about how a company really buys and pays.", { placeholder: "body" });
  text(s, "Process mining  ·  Compliance analytics  ·  Causal inference  ·  Machine learning", { x: MX, y: 6.55, w: 9, h: 0.35, fontSize: 13, color: MUTED });
  s.addNotes("This is a real event log from the purchasing system of a multinational coatings and paints company: 1.6 million ERP events on about 250,000 purchase order lines. Vendors and users are anonymised. It shows how I'd analyse an ERP process for a client: what happens, where control fails, what causes delay, and what to do about it.");

  // 2. Brief
  s = content("The brief", "A €997M order book and four hard questions", "Introduction");
  text(s, [{ text: "The process owner has compliance questions, and the finance team needs to plan. The answers sit in ", options: {} }, { text: "1,595,923 ERP events", options: { bold: true, color: HI } }, { text: " spread across 76,349 purchase orders from 1,975 vendors.", options: {} }],
    { x: MX, y: 1.75, w: 11.8, h: 0.75, fontSize: 17 });
  const qs = [
    ["LuRoute", "What really happens?", "The official process and the recorded one are rarely the same."],
    ["LuShieldCheck", "Where do controls fail?", "And how much money sits behind each failure?"],
    ["LuTimer", "When does cash go out?", "Payment dates and near-term outflow, with honest uncertainty."],
    ["LuFlaskConical", "What actually causes delay?", "Separating real causes from things that merely travel with them."],
  ];
  for (let i = 0; i < 4; i++) {
    const x = MX + i * 3.06, y = 2.85, w = 2.82, h = 3.6;
    card(s, x, y, w, h, "question card " + (i + 1));
    await iconTile(s, qs[i][0], x + 0.3, y + 0.35, HEX.cobalt);
    text(s, qs[i][1], { x: x + 0.3, y: y + 1.25, w: w - 0.6, h: 1.0, fontSize: 19, bold: true, color: HI, fontFace: HEAD });
    text(s, qs[i][2], { x: x + 0.3, y: y + 2.35, w: w - 0.6, h: 1.0, fontSize: 14 });
  }
  s.addNotes("The data is BPI Challenge 2019, published by 4TU.ResearchData under CC BY 4.0. The original challenge was framed by the company's process owner around compliance questions.");

  // 3. Answers
  s = content("The answers", "What the analysis found", "Introduction");
  const st = [
    [m1(comp.value_flagged), AMBER, "Controls", `of order value carries at least one control exception (${(100 * comp.n_flagged / comp.n_items).toFixed(1)}% of lines).`],
    [`${eff.dml_effect_days > 0 ? "+" : "−"}${Math.abs(eff.dml_effect_days).toFixed(1)} days`, TEAL, "Rework", `is the adjusted effect of order changes on payment. The naive gap of ${eff.naive_diff_days.toFixed(1)} days disappears.`],
    [`${(100 * modelErr).toFixed(1)}%`, COBALT, "Cash", `average miss on 30-day cash-out in three backtests, against ${(100 * naiveErr).toFixed(1)}% for a naive repeat.`],
    [`${km.toFixed(0)} days`, COBALT, "Timing", `median time to pay when open items count. Looking only at paid items gives ${D.kpis.median_days_paid_only.toFixed(0)}.`],
  ];
  for (let i = 0; i < 4; i++) {
    const x = MX + (i % 2) * 6.12, y = 1.85 + Math.floor(i / 2) * 2.5, w = 5.9, h = 2.3;
    card(s, x, y, w, h, "answer " + (i + 1));
    text(s, st[i][0], { x: x + 0.35, y: y + 0.4, w: 2.75, h: 1.1, fontSize: 38, bold: true, color: st[i][1], fontFace: HEAD, valign: "middle" });
    text(s, st[i][2].toUpperCase(), { x: x + 3.2, y: y + 0.42, w: 2.45, h: 0.3, fontSize: 11, bold: true, color: MUTED, charSpacing: 2 });
    text(s, st[i][3], { x: x + 3.2, y: y + 0.76, w: 2.45, h: 1.4, fontSize: 14 });
  }
  s.addNotes("Each number is tested on data the model did not see, or formally estimated with an interval. An exception is an indicator to review, not evidence of wrongdoing.");

  // 4. Trap
  pres.addSection({ title: "How it was built" });
  s = content("Know your data", "The field that would have broken everything", "How it was built");
  card(s, MX, 1.85, 5.9, 4.6, "trap numbers");
  text(s, "SUMMED NAIVELY", { x: MX + 0.4, y: 2.15, w: 5, h: 0.3, fontSize: 11, bold: true, color: MUTED, charSpacing: 2 });
  stat(s, "€5.7B", "apparent goods and invoice value", MX + 0.4, 2.45, 5, AMBER, 48);
  text(s, "TRUE ORDER BOOK", { x: MX + 0.4, y: 4.15, w: 5, h: 0.3, fontSize: 11, bold: true, color: MUTED, charSpacing: 2 });
  stat(s, "€997M", "total order value", MX + 0.4, 4.45, 5, TEAL, 48);
  card(s, 6.72, 1.85, 6.01, 4.6, "trap explanation");
  await iconTile(s, "LuSearchCheck", 7.05, 2.15, HEX.amber);
  text(s, "A name that misleads", { x: 7.85, y: 2.25, w: 4.6, h: 0.45, fontSize: 20, bold: true, color: HI, fontFace: HEAD });
  text(s, [
    { text: "“Cumulative net worth” repeats the line's running value on every event, so it isn't the amount of any one document.", options: { bullet: { indent: 15 }, breakLine: true } },
    { text: "A first version summed it, and the totals didn't reconcile to the order book. The check caught it.", options: { bullet: { indent: 15 }, breakLine: true } },
    { text: "Value-based matching isn't possible here, so controls test document counts and exposure uses order value.", options: { bullet: { indent: 15 } } },
  ], { x: 7.05, y: 3.0, w: 5.4, h: 3.2, fontSize: 15, paraSpaceAfter: 10 });
  s.addNotes("I keep this slide in because it's the real value of a careful analyst. A dashboard built on the naive sum would have looked fine and been wrong by a factor of nearly six. Reconciling totals back to a known figure is what exposed it.");

  // 5. Engineering
  s = content("Engineering", "An ERP data model you can trust", "How it was built");
  const layers = [
    ["LuFileCode", "Bronze", "Streamed, untouched", ["730 MB XES log parsed in about 30 seconds", "Checksum verified on every run", "External XML entities disabled"]],
    ["LuLayers", "Staging", "dbt on DuckDB", ["Typed events and order lines", "Implausible dates flagged, not dropped", "Every event numbered in process order"]],
    ["LuDatabase", "Marts", "Star schema", ["Document, line and event grains", "Vendor, user, activity and date dimensions", "Compliance, variants and process graph"]],
  ];
  for (let i = 0; i < 3; i++) {
    const x = MX + i * 4.1, y = 1.85, w = 3.85, h = 3.25;
    card(s, x, y, w, h, layers[i][1] + " layer");
    await iconTile(s, layers[i][0], x + 0.3, y + 0.3, i === 2 ? HEX.teal : HEX.cobalt);
    text(s, layers[i][1], { x: x + 1.1, y: y + 0.3, w: 2.5, h: 0.4, fontSize: 20, bold: true, color: HI, fontFace: HEAD });
    text(s, layers[i][2], { x: x + 1.1, y: y + 0.7, w: 2.5, h: 0.3, fontSize: 13, color: MUTED });
    text(s, layers[i][3].map((t, j) => ({ text: t, options: { bullet: { indent: 15 }, breakLine: j < 2 } })), { x: x + 0.3, y: y + 1.3, w: w - 0.6, h: 1.75, fontSize: 14, paraSpaceAfter: 7 });
  }
  const checks = [[`${D.dbt.models}`, "dbt models"], [`${D.dbt.tests_passed} / ${D.dbt.tests}`, "dbt tests pass, including a rule unit test"], ["1.6M", "events reconciled to source"]];
  checks.forEach(([n, l], i) => {
    const x = MX + i * 4.1;
    card(s, x, 5.3, 3.85, 1.15, "check " + (i + 1));
    text(s, n, { x: x + 0.3, y: 5.42, w: 1.6, h: 0.9, fontSize: 26, bold: true, color: TEAL, fontFace: HEAD, valign: "middle" });
    text(s, l, { x: x + 1.95, y: 5.42, w: 1.75, h: 0.9, fontSize: 13, valign: "middle" });
  });
  s.addNotes("The warehouse is a proper dbt project, so it transfers directly to Snowflake or BigQuery. If any test fails, the build stops before a single model runs. A unit test feeds the compliance rules known good and bad lines.");

  // 6. Process
  pres.addSection({ title: "What the data says" });
  const c0 = M.conformance.find((c) => c.flow === "three_way_before_gr");
  const c1 = M.conformance.find((c) => c.flow === "three_way_after_gr");
  s = content("Process mining", "Most waiting happens after the invoice is booked", "What the data says");
  card(s, MX, 1.85, 8.1, 4.6, "bottleneck card");
  s.addChart(pres.charts.BAR, [{ name: "Million item-days", labels: D.bottlenecks.labels.slice().reverse(), values: D.bottlenecks.values.slice().reverse() }], {
    x: MX + 0.2, y: 2.0, w: 7.7, h: 4.3, barDir: "bar", ...axis(), showTitle: true, title: "Waiting time by step, main flow (million item-days)",
    chartColors: [HEX.muted, HEX.muted, HEX.muted, HEX.muted, HEX.muted, HEX.amber], invertedColors: [HEX.muted], valAxisHidden: true, valGridLine: { style: "none" },
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0", dataLabelColor: HEX.text, dataLabelFontSize: 11, showLegend: false, barGapWidthPct: 45, valAxisMaxVal: 5.6,
  });
  card(s, 8.95, 1.85, 3.78, 4.6, "process callout");
  stat(s, "84%", "of paid lines in the main flow ran straight through", 9.25, 2.05, 3.2, TEAL);
  stat(s, c0.fitness.toFixed(2), "fitness of the discovered model on the main flow", 9.25, 3.5, 3.2, COBALT);
  stat(s, c1.fitness.toFixed(2), "on the GR-based flow: far less disciplined", 9.25, 4.95, 3.2, AMBER);
  s.addNotes("Models were discovered with the inductive miner and replayed against a sample. The wait after booking the invoice may simply reflect payment terms, which the log doesn't contain, so this is a question for the business rather than a verdict.");

  // 7. Compliance
  s = content("Compliance", `${m1(comp.value_flagged)} of orders carry a control exception`, "What the data says");
  card(s, MX, 1.85, 8.1, 4.6, "rules card");
  s.addChart(pres.charts.BAR, [{ name: "EUR million", labels: D.rules.labels.slice().reverse(), values: D.rules.values.slice().reverse() }], {
    x: MX + 0.2, y: 2.0, w: 7.7, h: 4.3, barDir: "bar", ...axis(), showTitle: true, title: "Order value behind each exception (EUR million)",
    chartColors: [HEX.amber], valAxisHidden: true, valGridLine: { style: "none" }, showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0",
    dataLabelColor: HEX.text, dataLabelFontSize: 11, showLegend: false, barGapWidthPct: 45, valAxisMaxVal: 140,
  });
  card(s, 8.95, 1.85, 3.78, 4.6, "compliance callout");
  stat(s, sod.toLocaleString("en-GB"), "lines with one person on both sides of a control", 9.25, 2.05, 3.2, AMBER);
  stat(s, "3 of 10", "controls recorded no exceptions at all, and goods receivers never pay", 9.25, 3.6, 3.2, TEAL);
  text(s, "An exception is a prompt to review, not proof of wrongdoing. Exposure is the order value of the line.", { x: 9.25, y: 5.3, w: 3.2, h: 0.95, fontSize: 12.5, color: MUTED, italic: true });
  s.addNotes("Ten controls were tested on every line. Saying which controls held is as useful as saying which failed: it shows where the system already enforces the rule and where people can work around it.");

  // 8. Causal
  pres.addSection({ title: "Advanced models" });
  s = content("Causal inference", "Reworked orders look slower. Rework isn't why", "Advanced models");
  card(s, MX, 1.85, 6.3, 4.6, "causal chart card");
  s.addChart(pres.charts.BAR, [{ name: "Days", labels: ["Naive gap", "Adjusted effect"], values: [Number(eff.naive_diff_days.toFixed(2)), Number(eff.dml_effect_days.toFixed(2))] }], {
    x: MX + 0.2, y: 2.0, w: 5.9, h: 4.3, barDir: "col", ...axis(), showTitle: true, title: "Extra unpaid days from an order change",
    chartColors: [HEX.muted, HEX.cobalt], invertedColors: [HEX.cobalt], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0", dataLabelColor: HEX.hi, dataLabelFontSize: 16,
    valAxisHidden: true, valGridLine: { style: "none" }, showLegend: false, barGapWidthPct: 70, valAxisMinVal: -2, valAxisMaxVal: 7,
  });
  card(s, 7.15, 1.85, 5.58, 4.6, "causal method");
  await iconTile(s, "LuFlaskConical", 7.45, 2.15, HEX.teal);
  text(s, "Three traps, handled", { x: 8.25, y: 2.25, w: 4.2, h: 0.45, fontSize: 20, bold: true, color: HI, fontFace: HEAD });
  text(s, [
    { text: "Confounding: ", options: { bold: true, color: HI } }, { text: "double machine learning adjusts for vendor, value and spend area.", options: { breakLine: true } },
    { text: "Immortal time: ", options: { bold: true, color: HI } }, { text: "only orders still unpaid at day 14 count, with changes inside those 14 days.", options: { breakLine: true } },
    { text: "Censoring: ", options: { bold: true, color: HI } }, { text: "the outcome is unpaid days in a fixed 180-day window.", options: { breakLine: true } },
    { text: "Result: ", options: { bold: true, color: TEAL } }, { text: `95% CI ${eff.ci_low.toFixed(1)} to +${eff.ci_high.toFixed(1)} days on ${eff.n.toLocaleString("en-GB")} lines. Placebo: ${eff.placebo_effect_days >= 0 ? "+" : ""}${eff.placebo_effect_days.toFixed(1)}.`, options: {} },
  ], { x: 7.45, y: 3.0, w: 5.0, h: 3.3, fontSize: 14.5, paraSpaceAfter: 9 });
  s.addNotes("This changes a decision. A team looking at the raw gap might launch a programme to cut order changes, and on this evidence it wouldn't speed up payment. Packaging is a possible exception, with a small positive effect, but segment results are noisier. A causal reading still assumes no major hidden confounder.");

  // 9. Survival + cash
  s = content("Survival analysis", "Forecasting cash from the open book", "Advanced models");
  card(s, MX, 1.85, 6.05, 4.6, "km card");
  const days = D.km.three_way_before_gr.day;
  s.addChart(pres.charts.LINE, [
    { name: "Invoice before receipt", labels: days.map(String), values: D.km.three_way_before_gr.v },
    { name: "Invoice after receipt", labels: days.map(String), values: D.km.three_way_after_gr.v },
  ], {
    x: MX + 0.2, y: 2.0, w: 5.65, h: 4.3, ...axis(), showTitle: true, title: "Share of items still unpaid, by days since order", chartColors: [HEX.cobalt, HEX.amber],
    lineSize: 2.5, lineDataSymbol: "none", valAxisLabelFormatCode: "0%", valAxisMaxVal: 1, showLegend: true, legendPos: "b", catAxisLabelFrequency: 5,
  });
  card(s, 6.9, 1.85, 5.83, 4.6, "cash card");
  const dates = bt.map((b) => b.as_of);
  s.addChart(pres.charts.BAR, [
    { name: "Forecast", labels: dates, values: bt.map((b) => Number((b.forecast_eur / 1e6).toFixed(1))) },
    { name: "Actual", labels: dates, values: bt.map((b) => Number((b.actual_eur / 1e6).toFixed(1))) },
    { name: "Last 30 days repeated", labels: dates, values: bt.map((b) => Number((b.naive_last_period_eur / 1e6).toFixed(1))) },
  ], {
    x: 7.05, y: 2.0, w: 5.53, h: 3.55, barDir: "col", barGrouping: "clustered", ...axis(), showTitle: true, title: "Next 30 days of payments (EUR million)",
    chartColors: [HEX.cobalt, HEX.hi, HEX.muted], showLegend: true, legendPos: "b", barGapWidthPct: 60, valAxisMinVal: 0,
  });
  text(s, `Next 30 days: about ${m1(cash[30])} expected to go out. Average backtest miss ${(100 * modelErr).toFixed(1)}% vs ${(100 * naiveErr).toFixed(1)}% naive.`, { x: 7.15, y: 5.6, w: 5.35, h: 0.7, fontSize: 13, color: TEXT });
  s.addNotes("Survival models learn from unfinished items as well as finished ones. Summing each open item's chance of being paid gives a cash forecast. The forecast model was picked on a separate earlier date, not on the dates shown. The naive baseline beat it on one of the three dates; on average the survival model is better.");

  // 10. Bayes
  const bm = M.bayes.meta;
  const bv = M.bayes.validation;
  s = content("Hierarchical Bayes", "Finding vendors that are truly a problem", "Advanced models");
  const bc = [["1", "median lines per vendor in the raw top 20: league tables crown one-order flukes", AMBER], [String(bm.median_items_bayes_top20), "median lines in the Bayesian top 20: real volume, worth a conversation", TEAL], [`${bm.top20_overlap_with_raw} of 20`, "vendors appear on both lists, so the choice of method changes who you call", COBALT]];
  for (let i = 0; i < 3; i++) {
    const x = MX + i * 4.1;
    card(s, x, 1.85, 3.85, 2.35, "bayes stat " + (i + 1));
    stat(s, bc[i][0], bc[i][1], x + 0.3, 2.0, 3.25, bc[i][2]);
  }
  card(s, MX, 4.4, 12.1, 2.05, "bayes validation");
  const rows = [[{ text: "Predicting each vendor's second half", options: { bold: true, color: MUTED } }, { text: "Log score (higher is better)", options: { bold: true, color: MUTED, align: "right" } }, { text: "Weighted error", options: { bold: true, color: MUTED, align: "right" } }]];
  bv.forEach((r, i) => rows.push([{ text: r.model, options: { bold: i === 0, color: i === 0 ? HI : TEXT } }, { text: r.log_score.toFixed(3), options: { align: "right", bold: i === 0, color: i === 0 ? HI : TEXT } }, { text: r.mae_weighted.toFixed(3), options: { align: "right", bold: i === 0, color: i === 0 ? HI : TEXT } }]));
  s.addTable(rows, { x: MX + 0.3, y: 4.55, w: 11.5, colW: [6.5, 3, 2], fontSize: 14, fontFace: "+mn-lt", color: TEXT, border: { type: "solid", pt: 0.5, color: HEX.line }, fill: { color: HEX.surface }, rowH: 0.42, margin: [0.04, 0.08, 0.04, 0.08] });
  s.addNotes("Partial pooling lets each vendor lean on the overall pattern in proportion to how little data it has. Fitted on the first half of the year and scored on the second, it beats both raw vendor rates and a single overall rate. R-hat is about 1.01, so the sampler converged.");

  // 11. Conformal + sequence
  s = content("Uncertainty and live prediction", "Predictions you can rely on", "Advanced models");
  card(s, MX, 1.85, 5.9, 4.6, "conformal card");
  await iconTile(s, "LuTarget", MX + 0.3, 2.15, HEX.teal);
  text(s, "Conformal prediction", { x: MX + 1.1, y: 2.25, w: 4.5, h: 0.45, fontSize: 20, bold: true, color: HI, fontFace: HEAD });
  text(s, "Does a “90% range” really hold 90% of the time?", { x: MX + 0.3, y: 3.0, w: 5.3, h: 0.4, fontSize: 15 });
  stat(s, `${(100 * conf[0].coverage).toFixed(0)}%`, "coverage from the raw quantile model", MX + 0.3, 3.5, 2.55, AMBER);
  stat(s, `${(100 * conf[2].coverage).toFixed(0)}%`, "after conformal calibration", MX + 3.1, 3.5, 2.5, TEAL);
  text(s, `Coverage on the smaller flow reaches ${(100 * conf[2].coverage_three_way_after_gr).toFixed(0)}%, and ranges are ${conf[2].avg_width_days.toFixed(0)} days wide: honest rather than impressive.`, { x: MX + 0.3, y: 5.2, w: 5.3, h: 1.0, fontSize: 13.5, color: MUTED, italic: true });
  card(s, 6.72, 1.85, 6.01, 4.6, "sequence card");
  await iconTile(s, "LuBrainCircuit", 7.02, 2.15, HEX.cobalt);
  text(s, "Deep sequence model", { x: 7.82, y: 2.25, w: 4.6, h: 0.45, fontSize: 20, bold: true, color: HI, fontFace: HEAD });
  text(s, "A PyTorch GRU reads events as they happen.", { x: 7.02, y: 3.0, w: 5.4, h: 0.4, fontSize: 15 });
  stat(s, `${seq.rem_mae_gru.toFixed(1)} d`, `error on time remaining, vs ${seq.rem_mae_baseline.toFixed(1)} days for the baseline`, 7.02, 3.5, 2.6, COBALT);
  stat(s, `${(100 * seq.next_acc_gru).toFixed(0)}%`, `next step correct, vs ${(100 * seq.next_acc_markov).toFixed(0)}% for a Markov chain`, 9.85, 3.5, 2.6, COBALT);
  text(s, "Tested on orders from a later period, with no future information in any prediction (unit-tested).", { x: 7.02, y: 5.2, w: 5.4, h: 1.0, fontSize: 13.5, color: MUTED, italic: true });
  s.addNotes("Conformal calibration measures the miss on held-back data and adjusts the range. It assumes the future resembles the calibration window, so a deployed version would recalibrate on a rolling basis. The sequence model's gains are largest mid-process, once the path has shown its hand.");

  // 12. Decision
  s = content("From score to decision", "A good model isn't automatically a business case", "Advanced models");
  card(s, MX, 1.85, 8.1, 4.6, "cost curve card");
  const lab = D.curve.x.map((v) => (100 * v).toFixed(1).replace(".0", "") + "%");
  s.addChart(pres.charts.LINE, [{ name: "Net saving (EUR)", labels: lab, values: D.curve.y }], {
    x: MX + 0.2, y: 2.0, w: 7.7, h: 4.3, ...axis(), showTitle: true, title: "Net saving by share of invoices reviewed (test period)", chartColors: [HEX.cobalt],
    lineSize: 2.5, lineDataSymbol: "none", showLegend: false, valAxisLabelFormatCode: "€#,##0", catAxisLabelFrequency: 4,
  });
  card(s, 8.95, 1.85, 3.78, 4.6, "decision callout");
  stat(s, `${(100 * best.share_reviewed).toFixed(1)}%`, "of invoices is the best share to review, not all of them", 9.25, 2.05, 3.2, TEAL);
  stat(s, `${Math.round(100 * best.corrections_caught / (am.base_rate * am.n_test))}%`, "of future corrections sit in that small slice", 9.25, 3.5, 3.2, COBALT);
  text(s, `ROC-AUC ${am.roc_auc.toFixed(2)}. Assumes €10 a review, €180 a correction and half prevented, which are inputs rather than findings. At €25 a review the saving falls to about €5k.`, { x: 9.25, y: 5.05, w: 3.2, h: 1.25, fontSize: 12.5, color: MUTED, italic: true });
  s.addNotes("This is the slide I'd most want a finance director to see. The model is decent, but whether to deploy it depends on what a review costs. The dashboard lets the client enter their own numbers.");

  // 13. Dashboard
  pres.addSection({ title: "Delivery" });
  s = content("Delivery", "A work queue, not just a report", "Delivery");
  const shots = [["dashboard_work_queue.jpg", "Work queue: open lines ranked, with the reason each one is there"], ["dashboard_causal.jpg", "Causal view: naive gap against the adjusted effect"]];
  shots.forEach(([f, cap], i) => {
    const x = MX + i * 6.12, w = 5.9, ih = ((w - 0.24) * 514) / 800;
    card(s, x, 1.85, w, ih + 0.75, "screenshot card " + (i + 1));
    s.addImage({ path: path.join(FIG, f), x: x + 0.12, y: 1.97, w: w - 0.24, h: ih, altText: cap });
    text(s, cap, { x: x + 0.3, y: 1.97 + ih + 0.14, w: w - 0.6, h: 0.35, fontSize: 13 });
  });
  text(s, "Nine tabs: Overview · Process · Compliance · Work queue · Payment timing · Vendors · Rework · Alerts · Data pipeline", { x: MX, y: 6.52, w: 12.1, h: 0.35, fontSize: 12.5, color: MUTED });
  s.addNotes("The work queue is the point of the project. It ranks open lines using control exceptions, vendor risk, an unusual path and age, and says why each line is there. A controller can act on it on Monday morning.");

  // 14. Recommendations
  s = content("Conclusions", "What I'd tell the CFO", "Delivery");
  const recs = [
    ["LuShieldAlert", "Review the leaking controls", `${sod.toLocaleString("en-GB")} lines had one person on both sides of a control. Three other controls held fully: find out why, and copy it.`],
    ["LuListChecks", "Look at the wait after booking", "That step holds the most waiting time. Check it against payment terms before changing anything."],
    ["LuBan", "Don't chase order changes", "Reducing rework is unlikely to speed payment. Spend that effort elsewhere, with Packaging the one area to look at."],
    ["LuChartLine", "Run cash from the open book", "A forecast built on line-level timing gives finance a 30-day view that's better than repeating last month."],
  ];
  for (let i = 0; i < 4; i++) {
    const x = MX + (i % 2) * 6.12, y = 1.85 + Math.floor(i / 2) * 2.4, w = 5.9, h = 2.2;
    card(s, x, y, w, h, "recommendation " + (i + 1));
    await iconTile(s, recs[i][0], x + 0.35, y + 0.4, HEX.teal);
    text(s, recs[i][1], { x: x + 1.2, y: y + 0.42, w: 4.4, h: 0.5, fontSize: 19, bold: true, color: HI, fontFace: HEAD });
    text(s, recs[i][2], { x: x + 1.2, y: y + 0.98, w: 4.4, h: 1.05, fontSize: 14.5 });
  }
  s.addNotes("Each recommendation ties to a finding. The second is deliberately cautious: the log doesn't contain payment terms, so the wait may be contractual.");

  // 15. Rigour
  s = content("How it's built", "What makes this work trustworthy", "Delivery");
  const pr = [
    ["LuClock", "Tested forward in time", "Every model is scored on later data, against something simple"],
    ["LuBug", "Reported what didn't work", "Limits and weak spots are stated, not hidden"],
    ["LuRepeat", "Reproducible", "One command from public download to dashboard, with identical results"],
    ["LuTestTube", "Tested", `${D.dbt.tests} dbt tests plus 12 Python tests, including recovering known effects`],
  ];
  for (let i = 0; i < 4; i++) {
    const y = 1.85 + i * 1.17;
    card(s, MX, y, 7.3, 1.02, "practice " + (i + 1));
    await iconTile(s, pr[i][0], MX + 0.25, y + 0.2, HEX.cobalt, 0.6);
    text(s, pr[i][1], { x: MX + 1.1, y: y + 0.14, w: 5.9, h: 0.36, fontSize: 16, bold: true, color: HI, fontFace: HEAD });
    text(s, pr[i][2], { x: MX + 1.1, y: y + 0.52, w: 5.95, h: 0.4, fontSize: 13 });
  }
  card(s, 8.15, 1.85, 4.58, 4.53, "toolkit");
  text(s, "TOOLKIT", { x: 8.45, y: 2.1, w: 3, h: 0.3, fontSize: 11, bold: true, color: MUTED, charSpacing: 2 });
  const chips = ["Python", "SQL", "dbt", "DuckDB", "pm4py", "lifelines", "NumPyro", "PyTorch", "scikit-learn", "SciPy", "Plotly", "Streamlit", "pytest", "GitHub Actions"];
  let cx = 8.45, cy = 2.55;
  chips.forEach((c) => {
    const cw = 0.28 + c.length * 0.105;
    if (cx + cw > 12.45) { cx = 8.45; cy += 0.56; }
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: cx, y: cy, w: cw, h: 0.42, rectRadius: 0.08, fill: { color: INK }, line: { color: LINE, width: 0.75 }, objectName: "chip " + c });
    s.addText(c, { isTextBox: true, x: cx, y: cy, w: cw, h: 0.42, fontSize: 12.5, color: HI, align: "center", valign: "middle", margin: 0 });
    cx += cw + 0.14;
  });
  s.addNotes("The same approach applies to any ERP: SAP, Oracle, Microsoft Dynamics or NetSuite. Each records who did what and when, and that's all this method needs.");

  // 16. Close
  s = pres.addSlide({ masterName: "Title", sectionTitle: "Delivery" });
  brandDot(s, MX, 1.68);
  s.addText("STRATUM", { placeholder: "eyebrow" });
  s.addText("What's your ERP not telling you?", { placeholder: "title" });
  s.addText("I turn the transaction history your systems already hold into clear answers on process, control and cash.", { placeholder: "body" });
  const contacts = [["LuGlobe", "stratumdata.org", "https://stratumdata.org"], ["LuMail", "stratumfreelance@gmail.com", "mailto:stratumfreelance@gmail.com"]];
  for (let i = 0; i < 2; i++) {
    const y = 5.75 + i * 0.55;
    s.addImage({ data: await icon(contacts[i][0], HEX.cobalt), x: MX, y: y + 0.04, w: 0.3, h: 0.3, altText: i ? "email" : "website" });
    text(s, [{ text: contacts[i][1], options: { hyperlink: { url: contacts[i][2] }, color: HI } }], { x: MX + 0.45, y, w: 5, h: 0.38, fontSize: 17, valign: "middle" });
  }
  s.addNotes("Close with the offer: the same analysis on the client's own ERP data, starting with a short scoping call.");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
}

build().catch((e) => { console.error(e); process.exit(1); });

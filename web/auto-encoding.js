/* ════════════════════════════════════════════════════════════════
   COMPRESSION PLAYGROUND · auto-encoding.js
   ─────────────────────────────────────────────────────────────────
   Shows `auto` as a per-row decision. `/api/auto-rows` runs
   auto_encode on every user of one demo-dataset column; this file
   paints the users as a grid coloured by the pipeline each one got,
   explains a selected user's pipeline from the shape of its data,
   and compares per-user auto against one fixed pipeline.
   ════════════════════════════════════════════════════════════════ */

'use strict';

// Columns worth showing first: each gets several different pipelines. The
// server's synthetic mixed-distribution column is prepended at init.
const SUGGESTED = ['is_like', 'date', 'tab', 'comment_stay_time', 'time_ms'];
const PALETTE_SIZE = 8;

const state = {
  columns: [],
  synthetic: null,     // name of the server's synthetic column
  column: null,
  lossy: false,
  data: null,
  colors: new Map(),   // pipeline → css colour
  selected: null,      // row index
  filter: null,        // pipeline being highlighted in the grid
  rowCache: new Map(), // `${column}|${lossy}|${row}` → values
  loadToken: 0,
};


// ─── data ────────────────────────────────────────────────────────

async function getJson(url) {
  const res = await fetch(url);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `request failed (${res.status})`);
  return body;
}

function columnUrl(column, extra = '') {
  return `/api/auto-rows?column=${encodeURIComponent(column)}&lossy=${state.lossy}${extra}`;
}

async function rowValues(row) {
  const key = `${state.column}|${state.lossy}|${row}`;
  if (!state.rowCache.has(key)) {
    const body = await getJson(columnUrl(state.column, `&row=${row}`));
    state.rowCache.set(key, body.values);
  }
  return state.rowCache.get(key);
}


// ─── formatting ──────────────────────────────────────────────────

function fmtBytes(n) {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(2)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n.toLocaleString()} B`;
}

function fmtNum(v) {
  if (typeof v !== 'number') return String(v);
  return Number.isInteger(v) ? v.toLocaleString() : v.toPrecision(3);
}

function pct(x) {
  const p = x * 100;
  return p >= 99.5 && p < 100 ? '>99%' : `${Math.round(p)}%`;
}

function pipelineLabel(scheme) {
  return scheme || 'raw';
}

function profileHtml(row) {
  if (!row.profile || !state.data.profiles) return '';
  return `<p class="au-profile"><b>Synthetic ${escapeHtml(row.profile)}.</b> ${escapeHtml(state.data.profiles[row.profile])}</p>`;
}

function colorFor(scheme) {
  return state.colors.get(scheme) || 'var(--pl-none)';
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}


// ─── why a pipeline won ──────────────────────────────────────────
// One plain-language line per step, grounded in the row's traits. Steps
// after the first act on the previous step's output, so they're described
// by what they do to it rather than by the raw sequence's traits.

function explainSteps(row) {
  const t = row.traits;
  const steps = row.scheme ? row.scheme.split('_') : [];
  if (steps.length === 0) {
    return [['raw', 'No pipeline came out smaller than the raw sequence, so it is stored as is.']];
  }
  return steps.map((step, i) => {
    const first = i === 0;
    switch (step) {
      case 'bm':
        return [step, t.distinct === 1
          ? `All ${row.length.toLocaleString()} values are ${fmtNum(t.dominant)}, and a bitmap of one bit per value is the smallest way to store them.`
          : `Only 0s and 1s across ${row.length.toLocaleString()} values, so each value fits in a single bit.`];
      case 'rle':
        return [step, first
          ? `The ${row.length.toLocaleString()} values form just ${t.runs.toLocaleString()} run${t.runs === 1 ? '' : 's'} of repeated values, so each run is stored once with its length.`
          : 'Repeated values left by the previous step are collapsed into runs.'];
      case 'nbp':
        return [step, first
          ? `${pct(t.dominant_share)} of values are ${fmtNum(t.dominant)}, so only the others are stored, with a bitmap marking where they go.`
          : 'Most entries in the run list are the same number, so only the exceptions are packed.'];
      case 'bp':
        return [step, first
          ? `Values range from ${fmtNum(t.min)} to ${fmtNum(t.max)}, so each is packed into the fewest bits that range needs.`
          : 'The remaining integers are packed into the fewest bits their range needs.'];
      case 'del':
        return [step, first
          ? 'Values move in small steps, so storing the difference from the previous value keeps the numbers small.'
          : 'Differences between neighbouring values are stored instead of the values.'];
      case 'stl': {
        const o = t.outliers;
        if (first && o) {
          const vals = o.values.map(v => fmtNum(Number(v))).join(', ');
          return [step, `${o.count} value${o.count === 1 ? '' : 's'} (${vals}) sit far outside the rest. They are set aside with their positions, so they no longer force every value to be stored with extra bits.`];
        }
        return [step, 'A few outliers are set aside so the remaining values span a narrower range.'];
      }
      case 'cat':
        return [step, `${t.distinct.toLocaleString()} distinct strings are replaced with small integer ids.`];
      case 'quant':
        return [step, 'Floats are rounded onto an 8-bit grid. This is lossy.'];
      case 'tbqm':
      case 'tbqp':
        return [step, 'The float vector is rotated and quantized against a codebook. This is lossy.'];
      default:
        return [step, ''];
    }
  });
}

function oneLineWhy(row) {
  return explainSteps(row).map(([, text]) => text).join(' ');
}


// ─── sequence strip ──────────────────────────────────────────────
// Each value is a vertical bar scaled between the row's min and max, so
// runs, sparsity and trends are visible at a glance.

function stripSvg(values, color, height) {
  const w = 600;
  const nums = values.map(v => (typeof v === 'number' ? v : NaN));
  const finite = nums.filter(Number.isFinite);
  if (finite.length === 0) {
    return `<svg class="au-strip" viewBox="0 0 ${w} ${height}" preserveAspectRatio="none" aria-hidden="true"></svg>`;
  }
  const lo = Math.min(...finite);
  const hi = Math.max(...finite);
  const span = hi - lo;
  const step = w / nums.length;
  const barW = Math.max(step * 0.8, 0.6);
  let d = '';
  nums.forEach((v, i) => {
    if (!Number.isFinite(v)) return;
    // A flat sequence has no shape to show; it draws as the baseline alone.
    const frac = span === 0 ? 0 : (v - lo) / span;
    const h = Math.max(frac * (height - 2), frac > 0 ? 1.5 : 0);
    if (h <= 0) return;
    const x = (i * step + step / 2).toFixed(2);
    d += `M${x} ${height}V${(height - h).toFixed(2)}`;
  });
  return `<svg class="au-strip" viewBox="0 0 ${w} ${height}" preserveAspectRatio="none" aria-hidden="true">
    <line x1="0" y1="${height - 0.5}" x2="${w}" y2="${height - 0.5}" stroke="var(--border)" stroke-width="1"/>
    <path d="${d}" stroke="${color}" stroke-width="${barW.toFixed(2)}" fill="none"/>
  </svg>`;
}

function inspectorHref(values, scheme) {
  const params = new URLSearchParams({
    values: JSON.stringify(values),
    pipeline: scheme || 'auto',
    lossy: String(state.lossy),
  });
  return `/inspector.html#${params.toString()}`;
}


// ─── render ──────────────────────────────────────────────────────

function renderHeadline() {
  const { data } = state;
  const encoded = data.breakdown.filter(b => b.scheme);
  const raw = data.breakdown.find(b => !b.scheme);
  const el = document.getElementById('auHeadline');
  const col = `<code>${escapeHtml(data.column)}</code>`;
  if (encoded.length === 0) {
    el.innerHTML = `No pipeline shrinks ${col} for any of the ${data.row_count} users, so every row stays raw.`
      + (data.column === 'embeddings' && !state.lossy ? ' Allow lossy to let auto quantize these floats.' : '');
  } else if (encoded.length === 1 && !raw) {
    el.innerHTML = `All ${data.row_count} users get <span class="num">${escapeHtml(encoded[0].scheme)}</span> for ${col}. Their data has the same shape, so there is nothing to adapt to.`;
  } else {
    el.innerHTML = `For ${col}, auto picked <span class="num">${encoded.length + (raw ? 1 : 0)} different pipelines</span> across ${data.row_count} users.`;
  }
}

function renderGrid() {
  const grid = document.getElementById('auGrid');
  grid.innerHTML = state.data.rows.map(r => `
    <button class="au-tile" data-row="${r.row}" style="background:${colorFor(r.scheme)}"
            aria-pressed="${r.row === state.selected}"
            title="User ${r.row}${r.profile ? ` (${escapeHtml(r.profile)})` : ''} · ${escapeHtml(pipelineLabel(r.scheme))} · ${fmtBytes(r.orig_bytes)} → ${fmtBytes(r.enc_bytes)}"
            aria-label="User ${r.row}, ${escapeHtml(pipelineLabel(r.scheme))}"></button>
  `).join('');
  applyFilter();
}

function applyFilter() {
  const grid = document.getElementById('auGrid');
  grid.classList.toggle('filtering', state.filter !== null);
  grid.querySelectorAll('.au-tile').forEach(tile => {
    const row = state.data.rows[Number(tile.dataset.row)];
    tile.classList.toggle('match', row.scheme === state.filter);
  });
  document.querySelectorAll('#auLegend button').forEach(btn => {
    btn.setAttribute('aria-pressed', String(btn.dataset.scheme === state.filter));
  });
}

function renderLegend() {
  document.getElementById('auLegend').innerHTML = state.data.breakdown.map(b => `
    <li>
      <button data-scheme="${escapeHtml(b.scheme)}" aria-pressed="false">
        <span class="au-swatch" style="background:${colorFor(b.scheme)}"></span>
        <span class="au-legend-name">${escapeHtml(pipelineLabel(b.scheme))}</span>
        <span class="au-legend-count">${b.count} user${b.count === 1 ? '' : 's'}</span>
      </button>
    </li>
  `).join('');
}

async function renderDetail() {
  const el = document.getElementById('auDetail');
  const row = state.data.rows[state.selected];
  const token = state.loadToken;
  el.innerHTML = `<p class="au-status">Loading user ${row.row}…</p>`;

  let values;
  try {
    values = await rowValues(row.row);
  } catch (err) {
    el.innerHTML = `<p class="au-status error">Couldn't load user ${row.row}: ${escapeHtml(err.message)}</p>`;
    return;
  }
  // A newer column load or selection has taken over.
  if (token !== state.loadToken || state.selected !== row.row) return;

  const color = colorFor(row.scheme);
  const steps = row.scheme ? row.scheme.split('_') : [];
  const chips = steps.length
    ? steps.map((s, i) => `${i ? '<span class="au-pipeline-arrow" aria-hidden="true">→</span>' : ''}<span class="scheme-chip"><span class="label">${escapeHtml(s)}</span></span>`).join('')
    : '<span class="au-raw-chip">stored raw</span>';
  const why = explainSteps(row).map(([step, text]) => `<li><code>${escapeHtml(step)}</code><span>${escapeHtml(text)}</span></li>`).join('');
  const ratio = row.enc_bytes > 0 ? row.orig_bytes / row.enc_bytes : 1;
  const t = row.traits;

  el.innerHTML = `
    <div class="au-detail-head">
      <h3 class="au-detail-user">User ${row.row}</h3>
      <span class="au-detail-len">${row.length.toLocaleString()} ${escapeHtml(row.type)} values</span>
    </div>
    ${profileHtml(row)}
    ${stripSvg(values, color, 72)}
    <div class="au-strip-caption">
      <span>${t.runs.toLocaleString()} run${t.runs === 1 ? '' : 's'} · ${t.distinct.toLocaleString()} distinct value${t.distinct === 1 ? '' : 's'}</span>
      <span>${t.distinct === 1 ? `every value is ${escapeHtml(fmtNum(t.dominant))}` : `range ${fmtNum(t.min)} to ${fmtNum(t.max)}`}</span>
    </div>
    <div class="au-pipeline">${chips}</div>
    <ul class="au-why">${why}</ul>
    <div class="au-bytes">
      <span class="au-bytes-from">${fmtBytes(row.orig_bytes)}</span>
      <span class="au-bytes-to">${fmtBytes(row.enc_bytes)}</span>
      ${ratio > 1 ? `<span class="au-bytes-ratio">${ratio.toFixed(1)}× smaller</span>` : ''}
      <a href="${inspectorHref(values, row.scheme)}">Step through in the inspector</a>
    </div>
  `;
}

// Three users with different pipelines, each the median user for its
// pipeline by compression ratio, so none of them is a cherry-picked extreme.
// If the user a single pipeline handles worst got a pipeline not already
// shown, it takes the last slot: that's the user auto helps most.
function pickContrastRows() {
  const picks = [];
  for (const b of state.data.breakdown) {
    if (picks.length === 3) break;
    const rows = state.data.rows
      .filter(r => r.scheme === b.scheme)
      .sort((a, c) => (a.orig_bytes / a.enc_bytes) - (c.orig_bytes / c.enc_bytes));
    picks.push(rows[Math.floor(rows.length / 2)]);
  }
  const worst = worstFixedRow();
  if (worst && picks.length > 1 && !picks.some(p => p.scheme === worst.scheme)) {
    picks[picks.length === 3 ? 2 : picks.length] = worst;
  }
  return picks;
}

// The user whose row is largest under the single best pipeline.
function worstFixedRow() {
  const rows = state.data.rows.filter(r => r.fixed_bytes !== undefined);
  if (rows.length === 0) return null;
  return rows.reduce((a, b) => (b.fixed_bytes > a.fixed_bytes ? b : a));
}

async function renderTrio() {
  const trio = document.getElementById('auTrio');
  const sub = document.getElementById('auTrioSub');
  const picks = pickContrastRows();
  const title = document.querySelector('.au-trio-title');
  const show = picks.length > 1;
  title.classList.toggle('hidden', !show);
  sub.classList.toggle('hidden', !show);
  trio.classList.toggle('hidden', !show);
  if (!show) return;

  const worst = worstFixedRow();
  sub.textContent = worst && picks.includes(worst)
    ? `A typical user for the most common pipelines in ${state.data.column}, and the user a single pipeline handles worst.`
    : `A typical user for each of the ${picks.length} most common pipelines in ${state.data.column}.`;
  const token = state.loadToken;
  let valueSets;
  try {
    valueSets = await Promise.all(picks.map(r => rowValues(r.row)));
  } catch {
    valueSets = picks.map(() => []);
  }
  if (token !== state.loadToken) return;

  trio.innerHTML = picks.map((r, i) => `
    <button class="au-card" data-row="${r.row}" style="--card-color:${colorFor(r.scheme)}">
      <div class="au-card-user">User ${r.row}${r.profile ? ` · ${escapeHtml(r.profile)}` : ''} · ${fmtBytes(r.orig_bytes)} → ${fmtBytes(r.enc_bytes)}</div>
      <div class="au-card-scheme">${escapeHtml(pipelineLabel(r.scheme))}</div>
      ${stripSvg(valueSets[i], colorFor(r.scheme), 36)}
      <p class="au-card-why">${escapeHtml(oneLineWhy(r))}</p>
    </button>
  `).join('');
}

function barRows(rows) {
  const max = Math.max(...rows.map(r => r.bytes), 1);
  return rows.map(r => `
    <div class="au-bar-row${r.auto ? ' auto' : ''}">
      <div class="au-bar-label">${escapeHtml(r.label)}<small>${escapeHtml(r.sub)}</small></div>
      <div class="au-bar-track"><div class="au-bar-fill" style="width:${Math.max((r.bytes / max) * 100, 0.4)}%"></div></div>
      <div class="au-bar-value">${fmtBytes(r.bytes)}</div>
    </div>
  `).join('');
}

function renderSavings() {
  const { totals, fixed, column, breakdown } = state.data;
  const best = fixed[0];
  const nPipelines = `${breakdown.length} pipeline${breakdown.length === 1 ? '' : 's'}`;

  document.getElementById('auBars').innerHTML = barRows([
    { label: 'Raw', sub: 'no encoding', bytes: totals.original },
    best && { label: 'One pipeline', sub: best.scheme, bytes: best.bytes },
    { label: 'Auto, per user', sub: nPipelines, bytes: totals.auto, auto: true },
  ].filter(Boolean));
  document.getElementById('auMaxBars').innerHTML = barRows([
    { label: 'Raw', sub: 'no encoding', bytes: totals.max_original },
    best && { label: 'One pipeline', sub: best.scheme, bytes: best.max_bytes },
    { label: 'Auto, per user', sub: nPipelines, bytes: totals.max_auto, auto: true },
  ].filter(Boolean));

  const note = document.getElementById('auSavingsNote');
  const col = `<code>${escapeHtml(column)}</code>`;
  const vsRaw = totals.auto > 0 ? totals.original / totals.auto : 1;
  if (!best) {
    note.innerHTML = `No pipeline helps ${col}, so auto leaves it raw rather than making it bigger.`;
  } else if (best.bytes <= totals.auto) {
    note.innerHTML = `Every user in ${col} shares the same pipeline, so choosing per user matches the single pipeline exactly. Auto still saves you from picking it by hand: ${vsRaw.toFixed(1)}× smaller than raw.`;
  } else {
    const saved = 1 - totals.auto / best.bytes;
    const maxSaved = 1 - totals.max_auto / best.max_bytes;
    const worst = worstFixedRow();
    const who = worst && worst.profile ? ` (a ${escapeHtml(worst.profile)} user)` : '';
    note.innerHTML = `Choosing per user makes ${col} <strong>${pct(saved)} smaller</strong> in total than the best single pipeline, <code>${escapeHtml(best.scheme)}</code>.`
      + (maxSaved > 0.005
        ? ` The largest row drops from ${fmtBytes(best.max_bytes)}${who} to ${fmtBytes(totals.max_auto)}, <strong>${pct(maxSaved)} smaller</strong>.`
        : ` The largest row is the same size either way.`);
  }

  // Invite a switch to the synthetic feature from real ones.
  const showSwitch = state.synthetic && column !== state.synthetic;
  document.getElementById('auSwitchWrap').classList.toggle('hidden', !showSwitch);

  renderTail();
}


// ─── per-user chart ──────────────────────────────────────────────
// One column per user, sorted by size under the single pipeline. The
// single pipeline is a recessive grey bar; auto's size sits in front of it.
// Dashed lines mark each approach's largest row.

function niceStep(max, ticks) {
  const raw = max / ticks;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  return (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
}

function barPath(x, y, w, base) {
  // Rounded data-end, square at the baseline.
  const r = Math.min(2, w / 2, (base - y) / 2);
  if (r <= 0) return `M${x} ${base}H${x + w}V${y}H${x}Z`;
  return `M${x} ${base}V${y + r}Q${x} ${y} ${x + r} ${y}H${x + w - r}Q${x + w} ${y} ${x + w} ${y + r}V${base}Z`;
}

function renderTail() {
  const wrap = document.getElementById('auTail');
  const plot = document.getElementById('auTailPlot');
  const rows = state.data.rows.filter(r => r.fixed_bytes !== undefined);
  const best = state.data.fixed[0];
  const differs = best && best.bytes > state.data.totals.auto;
  wrap.classList.toggle('hidden', !differs);
  if (!differs) return;

  const sorted = [...rows].sort((a, b) => b.fixed_bytes - a.fixed_bytes || b.enc_bytes - a.enc_bytes);
  document.getElementById('auTailTitle').textContent = `Every user's ${state.data.column}, encoded`;
  document.getElementById('auTailFixedName').textContent = `one pipeline (${best.scheme})`;

  const W = Math.max(plot.clientWidth, 280);
  const H = 240;
  const m = { top: 18, right: 4, bottom: 22, left: 52 };
  const iw = W - m.left - m.right;
  const ih = H - m.top - m.bottom;
  const base = m.top + ih;
  const maxY = Math.max(...sorted.map(r => r.fixed_bytes), 1);
  // Ticks step in KB once the axis passes 2 KB, so labels share one unit.
  const unit = maxY >= 2048 ? 1024 : 1;
  const step = niceStep(maxY / unit, 4) * unit;
  const tick = v => (unit === 1 ? `${v.toLocaleString()} B` : `${+(v / 1024).toFixed(1)} KB`);
  const top = Math.ceil(maxY / step) * step;
  const y = v => m.top + ih - (v / top) * ih;
  const slot = iw / sorted.length;
  const gap = slot > 4 ? 1 : 0;
  const fw = Math.max(slot - gap * 2, 0.8);
  const aw = Math.max(fw * 0.55, 0.8);

  let grid = '';
  for (let v = 0; v <= top + 1e-9; v += step) {
    grid += `<line x1="${m.left}" x2="${W - m.right}" y1="${y(v)}" y2="${y(v)}" stroke="var(--rule)" stroke-width="1"/>`;
    grid += `<text x="${m.left - 8}" y="${y(v) + 3.5}" text-anchor="end">${tick(v)}</text>`;
  }

  let bars = '';
  let hits = '';
  sorted.forEach((r, i) => {
    const x = m.left + i * slot;
    bars += `<path d="${barPath(x + gap, y(r.fixed_bytes), fw, base)}" fill="var(--viz-fixed)"/>`;
    bars += `<path d="${barPath(x + (slot - aw) / 2, y(r.enc_bytes), aw, base)}" fill="var(--viz-auto)"/>`;
    hits += `<rect class="hit" data-i="${i}" x="${x}" y="${m.top}" width="${slot}" height="${ih}"/>`;
  });

  // Reference lines for the largest row under each approach.
  const maxFixed = best.max_bytes;
  const maxAuto = state.data.totals.max_auto;
  const yf = y(maxFixed);
  const ya = y(maxAuto);
  const labelX = W - m.right;
  const autoBelow = ya - yf < 16;
  const refs = `
    <line x1="${m.left}" x2="${W - m.right}" y1="${yf}" y2="${yf}" stroke="var(--muted)" stroke-dasharray="4 4" stroke-width="1"/>
    <text class="ref-label" x="${labelX}" y="${yf - 6}" text-anchor="end">largest row, one pipeline: ${fmtBytes(maxFixed)}</text>
    <line x1="${m.left}" x2="${W - m.right}" y1="${ya}" y2="${ya}" stroke="var(--accent)" stroke-dasharray="4 4" stroke-width="1"/>
    <text class="ref-label" x="${labelX}" y="${autoBelow ? ya + 14 : ya - 6}" text-anchor="end" style="fill:var(--accent-strong)">largest row, auto: ${fmtBytes(maxAuto)}</text>`;

  plot.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" height="${H}" role="img"
         aria-label="Encoded size per user under ${escapeHtml(best.scheme)} and under auto. Largest row: ${fmtBytes(maxFixed)} with one pipeline, ${fmtBytes(maxAuto)} with auto.">
      ${grid}
      <line x1="${m.left}" x2="${W - m.right}" y1="${base}" y2="${base}" stroke="var(--border-strong)" stroke-width="1"/>
      ${bars}
      ${refs}
      <text x="${m.left}" y="${H - 4}">largest</text>
      <text x="${W - m.right}" y="${H - 4}" text-anchor="end">smallest</text>
      ${hits}
    </svg>
    <div class="au-tip hidden" id="auTip"></div>`;
  plot._sorted = sorted;

  document.getElementById('auTailTable').innerHTML = `
    <thead><tr><th>User</th>${state.data.profiles ? '<th>Profile</th>' : '<th></th>'}<th>Auto pipeline</th><th>${escapeHtml(best.scheme)}</th><th>Auto</th></tr></thead>
    <tbody>${sorted.map(r => `<tr><td>${r.row}</td><td>${escapeHtml(r.profile || '')}</td><td>${escapeHtml(pipelineLabel(r.scheme))}</td><td>${fmtBytes(r.fixed_bytes)}</td><td>${fmtBytes(r.enc_bytes)}</td></tr>`).join('')}</tbody>`;
}

function showTip(hit) {
  const plot = document.getElementById('auTailPlot');
  const tip = document.getElementById('auTip');
  const r = plot._sorted[Number(hit.dataset.i)];
  plot.querySelectorAll('.hit.active').forEach(h => h.classList.remove('active'));
  hit.classList.add('active');
  tip.innerHTML = `
    <div><b>User ${r.row}</b>${r.profile ? ` <span class="muted">${escapeHtml(r.profile)}</span>` : ''}</div>
    <div class="au-tip-row"><i style="background:var(--viz-fixed)"></i>${escapeHtml(state.data.fixed[0].scheme)}: ${fmtBytes(r.fixed_bytes)}</div>
    <div class="au-tip-row"><i style="background:var(--viz-auto)"></i>auto (${escapeHtml(pipelineLabel(r.scheme))}): ${fmtBytes(r.enc_bytes)}</div>`;
  tip.classList.remove('hidden');
  const hb = hit.getBoundingClientRect();
  const pb = plot.getBoundingClientRect();
  const tw = tip.offsetWidth;
  let left = hb.left - pb.left + hb.width / 2 + 10;
  if (left + tw > pb.width) left = hb.left - pb.left - tw - 10;
  tip.style.left = `${Math.max(0, left)}px`;
  tip.style.top = '8px';
}

function hideTip() {
  const tip = document.getElementById('auTip');
  if (tip) tip.classList.add('hidden');
  document.querySelectorAll('#auTailPlot .hit.active').forEach(h => h.classList.remove('active'));
}

// The intro code sample quotes real pipelines from is_like.
function renderCodeRows() {
  const target = document.getElementById('auCodeRows');
  if (state.data.column !== 'is_like' || target.dataset.filled) return;
  const lines = pickContrastRows().map(r =>
    `<span class="c"># user ${String(r.row).padEnd(3)} is_like_enc → [ …, "${escapeHtml(pipelineLabel(r.scheme))}", … ]</span>`);
  target.innerHTML = lines.join('\n');
  target.dataset.filled = '1';
}

function setStatus(label, detail) {
  document.getElementById('statusLabel').textContent = label;
  document.getElementById('statusDetail').textContent = detail;
}


// ─── flow ────────────────────────────────────────────────────────

async function loadColumn(column) {
  const token = ++state.loadToken;
  state.column = column;
  state.filter = null;
  document.getElementById('auColumn').value = column;
  document.querySelectorAll('.au-pick').forEach(p => p.setAttribute('aria-pressed', String(p.dataset.col === column)));

  const status = document.getElementById('auStatus');
  status.className = 'au-status';
  status.textContent = `Running auto on every user's ${column} sequence…`;
  status.classList.remove('hidden');
  setStatus('ENCODING', `auto_encode · ${column}`);

  let data;
  try {
    data = await getJson(columnUrl(column));
  } catch (err) {
    if (token !== state.loadToken) return;
    status.classList.add('error');
    status.textContent = `Couldn't encode ${column}: ${err.message}. Check that the playground server is running.`;
    setStatus('ERROR', err.message);
    return;
  }
  if (token !== state.loadToken) return;

  state.data = data;
  state.colors = new Map();
  let i = 0;
  for (const b of data.breakdown) {
    state.colors.set(b.scheme, b.scheme ? `var(--pl-${Math.min(i++, PALETTE_SIZE - 1)})` : 'var(--pl-none)');
  }

  status.classList.add('hidden');
  document.getElementById('auExplorer').classList.remove('hidden');
  renderHeadline();
  renderLegend();
  document.getElementById('auGridSource').textContent = data.profiles
    ? 'one synthetic user drawn from four watch-time profiles'
    : 'one user from the KuaiRand demo sample';
  // Open on the user auto helps most when the trio features them, otherwise
  // on the most varied typical user, so the first sequence shown has shape.
  const picks = pickContrastRows();
  const worst = worstFixedRow();
  state.selected = (worst && picks.includes(worst) ? worst
    : picks.reduce((a, b) => (b.traits.runs > a.traits.runs ? b : a))).row;
  renderGrid();
  renderSavings();
  renderCodeRows();
  renderDetail();
  renderTrio();
  setStatus('AUTO', `${data.column} · ${data.row_count} users · ${data.breakdown.length} pipelines · ${data.elapsed_ms.toLocaleString()} ms`);
}

function selectRow(row) {
  state.selected = row;
  document.querySelectorAll('#auGrid .au-tile').forEach(tile => {
    tile.setAttribute('aria-pressed', String(Number(tile.dataset.row) === row));
  });
  renderDetail();
}

function wire() {
  document.getElementById('auGrid').addEventListener('click', e => {
    const tile = e.target.closest('.au-tile');
    if (tile) selectRow(Number(tile.dataset.row));
  });
  document.getElementById('auTrio').addEventListener('click', e => {
    const card = e.target.closest('.au-card');
    if (!card) return;
    selectRow(Number(card.dataset.row));
    document.getElementById('auDetail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
  document.getElementById('auLegend').addEventListener('click', e => {
    const btn = e.target.closest('button');
    if (!btn) return;
    const scheme = btn.dataset.scheme;
    state.filter = state.filter === scheme ? null : scheme;
    applyFilter();
  });
  document.getElementById('auColumn').addEventListener('change', e => loadColumn(e.target.value));
  document.getElementById('auSwitchBtn').addEventListener('click', () => {
    loadColumn(state.synthetic);
    document.getElementById('auSavingsSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  const plot = document.getElementById('auTailPlot');
  plot.addEventListener('mouseover', e => {
    const hit = e.target.closest('.hit');
    if (hit) showTip(hit);
  });
  plot.addEventListener('mouseleave', hideTip);
  plot.addEventListener('click', e => {
    const hit = e.target.closest('.hit');
    if (!hit) return;
    selectRow(plot._sorted[Number(hit.dataset.i)].row);
    document.getElementById('auDetail').scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
  let resizeTimer;
  new ResizeObserver(() => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (state.data) renderTail(); }, 120);
  }).observe(plot);
  document.getElementById('auPicks').addEventListener('click', e => {
    const pick = e.target.closest('.au-pick');
    if (pick) loadColumn(pick.dataset.col);
  });
  document.getElementById('auLossy').addEventListener('change', e => {
    state.lossy = e.target.checked;
    loadColumn(state.column);
  });
}

async function init() {
  wire();
  let meta;
  try {
    meta = await getJson('/api/auto-rows');
  } catch (err) {
    const status = document.getElementById('auStatus');
    status.classList.add('error');
    status.textContent = `Couldn't load the demo dataset: ${err.message}. Start the playground server with python web/server.py.`;
    setStatus('ERROR', err.message);
    return;
  }
  state.columns = meta.columns;
  state.synthetic = meta.synthetic || null;
  if (state.synthetic) SUGGESTED.unshift(state.synthetic);
  document.getElementById('auColumn').innerHTML = meta.columns
    .map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
  document.getElementById('auPicks').innerHTML = SUGGESTED
    .filter(c => meta.columns.includes(c))
    .map(c => `<button class="au-pick" data-col="${escapeHtml(c)}" aria-pressed="false">${escapeHtml(c)}</button>`).join('');
  // Keep the synthetic feature easy to find at the top of the dropdown.
  if (state.synthetic) {
    const sel = document.getElementById('auColumn');
    const opt = sel.querySelector(`option[value="${state.synthetic}"]`);
    if (opt) { opt.textContent = `${state.synthetic} (synthetic)`; sel.prepend(opt); }
  }
  // `#column=<name>` opens a specific feature, so views can be linked.
  const fromHash = new URLSearchParams(location.hash.slice(1)).get('column');
  loadColumn(meta.columns.includes(fromHash) ? fromHash : meta.default);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

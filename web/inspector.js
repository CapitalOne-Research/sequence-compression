/* ════════════════════════════════════════════════════════════════
   COMPRESSION PLAYGROUND · inspector.js
   ─────────────────────────────────────────────────────────────────
   Step-through inspector. User types a sequence, picks a pipeline,
   and the server (`/api/steps`) returns every intermediate state.
   This file owns the UI: chip composer, input parsing, and the
   per-scheme step visualisations.
   ════════════════════════════════════════════════════════════════ */

'use strict';

const SCHEME_INFO = {
  cat:   { name: 'Categorical',     desc: 'string channel ID → integer dictionary',  group: 'transform' },
  quant: { name: 'Quantization',    desc: 'float score → 8-bit uint (lossy)',         group: 'transform', lossy: true },
  tbqm:  { name: 'TurboQuant MSE',  desc: 'float vector → base64 (rotation + codebook, lossy)', group: 'transform', lossy: true },
  tbqp:  { name: 'TurboQuant Prod', desc: 'float vector → base64 + QJL residual (inner-product optimal, lossy)', group: 'transform', lossy: true },
  del:   { name: 'Delta',           desc: 'each value − its predecessor (timestamps)',group: 'reduce' },
  rle:   { name: 'Run-Length',      desc: 'collapse repeated-value runs',             group: 'reduce' },
  stl:   { name: 'Sentinel',        desc: 'strip outliers (IQR method)',              group: 'reduce' },
  bp:    { name: 'Bit-Pack',        desc: 'pack ints into base64 bitstream',          group: 'pack' },
  bm:    { name: 'Bitmap',          desc: 'binary interaction → packed bits (base64)',group: 'pack' },
  nbp:   { name: 'Nullmap Bit-Pack',desc: 'sparse counts → dominant + nullmap',       group: 'pack' },
};

const SCHEME_GROUPS = [
  ['Transform · change representation', ['cat', 'quant', 'tbqm', 'tbqp']],
  ['Reduce · shrink range or run length',['del', 'rle', 'stl']],
  ['Pack · bit-level base64 output',    ['bp', 'bm', 'nbp']],
];

// Each preset is shaped so `auto` composes a deep pipeline: long value runs
// (cat_rle_bp), regular-then-bursty intervals (del_rle_nbp), or smooth drift
// (quant_del_bp / del_rle_tbqm). `binary` stays a single-step bitmap contrast.
const PRESETS = {
  categorical: ["WEB","WEB","WEB","WEB","WEB","WEB","WEB","WEB","WEB","MOBILE","MOBILE","MOBILE","MOBILE","MOBILE","MOBILE","MOBILE","WEB","WEB","WEB","WEB","WEB","APP","APP","APP","APP","APP","APP","APP","APP","APP","APP","APP","MOBILE","MOBILE","MOBILE","MOBILE","MOBILE","MOBILE","WEB","WEB","WEB","WEB","WEB","WEB","WEB","WEB","APP","APP","APP","APP","APP","APP","APP","MOBILE","MOBILE","MOBILE","MOBILE","MOBILE"],
  item_ids:    ["ITEM_00423","ITEM_00423","ITEM_00423","ITEM_00423","ITEM_00423","ITEM_00423","ITEM_01187","ITEM_01187","ITEM_01187","ITEM_01187","ITEM_01187","ITEM_01187","ITEM_01187","ITEM_01187","ITEM_00423","ITEM_00423","ITEM_00423","ITEM_00423","ITEM_00423","ITEM_02341","ITEM_02341","ITEM_02341","ITEM_02341","ITEM_02341","ITEM_02341","ITEM_02341","ITEM_02341","ITEM_02341","ITEM_01187","ITEM_01187","ITEM_01187","ITEM_01187","ITEM_01187","ITEM_01187","ITEM_01187","ITEM_00012","ITEM_00012","ITEM_00012","ITEM_00012","ITEM_00012","ITEM_00012","ITEM_02341","ITEM_02341","ITEM_02341","ITEM_02341","ITEM_02341"],
  categories:  ["ELECTRONICS","ELECTRONICS","ELECTRONICS","ELECTRONICS","ELECTRONICS","ELECTRONICS","ELECTRONICS","BOOKS","BOOKS","BOOKS","BOOKS","BOOKS","ELECTRONICS","ELECTRONICS","ELECTRONICS","ELECTRONICS","ELECTRONICS","ELECTRONICS","CLOTHING","CLOTHING","CLOTHING","CLOTHING","CLOTHING","CLOTHING","CLOTHING","CLOTHING","CLOTHING","HOME","HOME","HOME","HOME","HOME","CLOTHING","CLOTHING","CLOTHING","CLOTHING","CLOTHING","CLOTHING","CLOTHING","SPORTS","SPORTS","SPORTS","SPORTS","SPORTS","SPORTS","BOOKS","BOOKS","BOOKS","BOOKS","BOOKS"],
  binary:      [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0],
  timestamps:  [1700000000000,1700000060000,1700000120000,1700000180000,1700000240000,1700000300000,1700000360000,1700000420000,1700000480000,1700000780000,1700001080000,1700001380000,1700001680000,1700001980000,1700002280000,1700002340000,1700002400000,1700002460000,1700002520000,1700002580000,1700002640000,1700002700000,1700002760000,1700002820000,1700002880000,1700003000000,1700003120000,1700003240000,1700003360000,1700003480000,1700003540000,1700003600000,1700003660000,1700003720000,1700003780000,1700003840000,1700003900000,1700003960000,1700004020000,1700004320000,1700004620000,1700004920000,1700005220000],
  counts:      [0,0,0,0,0,0,2,2,2,0,0,0,0,0,0,0,0,1,0,0,0,0,0,3,3,3,3,0,0,0,0,0,0,0,5,0,0,0,0,0,0],
  ratings:     [5,5,5,5,5,5,4,4,4,4,4,5,5,5,5,5,5,5,3,3,3,3,4,4,4,4,4,4,5,5,5,5,5,5,5,5,2,2,2,5,5,5,5,5],
  dwell:       [15000,15000,15000,15000,15000,45000,45000,45000,45000,15000,15000,15000,15000,15000,15000,90000,90000,90000,30000,30000,30000,30000,30000,30000,30000,15000,15000,15000,15000,15000,60000,60000,60000,60000,30000,30000,30000,30000,30000,30000],
  floats:      [0.7,0.7005,0.701,0.7015,0.702,0.7025,0.703,0.7035,0.704,0.7045,0.705,0.7055,0.706,0.7065,0.707,0.7075,0.708,0.7085,0.709,0.7095,0.71,0.7105,0.711,0.7115,0.712,0.7125,0.713,0.7135,0.714,0.7145,0.715,0.7155,0.716,0.7165,0.717,0.7175,0.718,0.7185,0.719,0.7195,0.72,0.7205,0.721,0.7215,0.722,0.7225,0.723,0.7235,0.724,0.7245,0.725,0.7255,0.726,0.7265,0.727,0.7275,0.728,0.7285,0.729,0.7295],
  scores:      [0.985,0.9841,0.9832,0.9823,0.9814,0.9805,0.9796,0.9787,0.9778,0.9769,0.976,0.9751,0.9742,0.9733,0.9724,0.9715,0.9706,0.9697,0.9688,0.9679,0.967,0.9661,0.9652,0.9643,0.9634,0.9625,0.9616,0.9607,0.9598,0.9589,0.958,0.9571,0.9562,0.9553,0.9544,0.9535,0.9526,0.9517,0.9508,0.9499,0.949,0.9481,0.9472,0.9463,0.9454,0.9445,0.9436,0.9427,0.9418,0.9409,0.94,0.9391,0.9382,0.9373,0.9364,0.9355,0.9346,0.9337,0.9328,0.9319],
};

const state = {
  pipeline: ['cat', 'rle', 'bp'],
  lossy: true,
};


// ─── input parsing ────────────────────────────────────────────────

function parseInput(text) {
  const trimmed = text.trim();
  if (!trimmed) return [];

  // 1) JSON array form
  if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) return parsed;
    } catch {}
    // tolerate Python-repr / numpy-repr too — split on commas / whitespace
  }

  // 2) split on commas (preferring) or newlines
  const inner = trimmed.startsWith('[') && trimmed.endsWith(']')
    ? trimmed.slice(1, -1)
    : trimmed;

  // commas if present, else newlines, else whitespace
  let separator = /\n+/;
  if (inner.includes(',')) separator = /,/;
  else if (!/\n/.test(inner) && /\s/.test(inner)) separator = /\s+/;

  const parts = inner.split(separator).map(s => s.trim()).filter(Boolean);
  return parts.map(p => {
    // strip wrapping quotes
    if (p.length >= 2 &&
        ((p.startsWith('"') && p.endsWith('"')) ||
         (p.startsWith("'") && p.endsWith("'")))) {
      return p.slice(1, -1);
    }
    // numeric coerce when the whole token is a number
    if (/^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(p)) {
      const n = Number(p);
      if (!Number.isNaN(n)) return n;
    }
    return p;
  });
}


// ─── chip composer ────────────────────────────────────────────────

function renderChips() {
  const chipsEl = document.getElementById('pgChips');
  const addEl = document.getElementById('pgAddSlot');

  if (state.pipeline.length === 0) {
    chipsEl.innerHTML = `<span class="pipeline-empty">⌁ pass through</span>`;
  } else {
    chipsEl.innerHTML = state.pipeline.map((step, i) => {
      const arrow = i > 0 ? `<span class="pipeline-arrow">▸</span>` : '';
      if (step === 'auto') {
        return `${arrow}<span class="scheme-chip auto-chip" title="Auto-discover">
          <span class="label"><span class="auto-glyph">✦</span> auto</span>
          <span class="x" data-idx="${i}" aria-label="remove">×</span>
        </span>`;
      }
      const info = SCHEME_INFO[step];
      const title = info ? `${info.name} — ${info.desc}` : step;
      return `${arrow}<span class="scheme-chip" title="${escapeAttr(title)}">
        <span class="label">${escapeHtml(step)}</span>
        <span class="x" data-idx="${i}" aria-label="remove">×</span>
      </span>`;
    }).join('');
  }

  const hasAuto = state.pipeline.includes('auto');
  if (hasAuto) {
    addEl.innerHTML = '';
  } else {
    addEl.innerHTML = renderAddMenu();
  }

  // wire chip × handlers
  chipsEl.querySelectorAll('.scheme-chip .x').forEach(el => {
    el.addEventListener('click', () => {
      const idx = parseInt(el.dataset.idx, 10);
      state.pipeline.splice(idx, 1);
      renderChips();
    });
  });

  // position the fixed menu below its summary button when opened
  addEl.querySelectorAll('details.add-scheme').forEach(details => {
    details.addEventListener('toggle', () => {
      if (!details.open) return;
      const summary = details.querySelector('summary');
      const menu = details.querySelector('.add-scheme-menu');
      if (!summary || !menu) return;
      const rect = summary.getBoundingClientRect();
      const menuHeight = menu.offsetHeight || 400;
      menu.style.top  = `${rect.top - menuHeight - 4}px`;
      menu.style.left = `${rect.left}px`;
    });
  });

  // wire add-menu items
  addEl.querySelectorAll('.add-scheme-item').forEach(el => {
    el.addEventListener('click', e => {
      e.stopPropagation();
      const code = el.dataset.code;
      if (code === 'auto' || state.pipeline.includes('auto')) {
        state.pipeline = [code];
      } else {
        state.pipeline.push(code);
      }
      renderChips();
      addEl.querySelectorAll('details.add-scheme').forEach(d => d.open = false);
    });
  });

  scheduleInspectorWarnings();
}

// ─── improper-pipeline warnings (server-validated) ────────────────
// Validation lives on the server (/api/validate → same transition table the
// encoder uses); the inspector just sends the pasted values + pipeline and
// paints the returned warnings. Re-runs on pipeline edits and input edits.

let _warnToken = 0;
let _warnTimer = null;

function scheduleInspectorWarnings() {
  clearTimeout(_warnTimer);
  _warnTimer = setTimeout(refreshInspectorWarnings, 120);
}

async function refreshInspectorWarnings() {
  const box = document.getElementById('pgPipelineWarnings');
  if (!box) return;

  const pipeline = state.pipeline.includes('auto')
    ? 'auto'
    : state.pipeline.join('_');
  if (!pipeline || pipeline === 'auto') {
    box.innerHTML = '';
    return;
  }

  let values = [];
  try { values = parseInput(document.getElementById('pgInput').value); } catch { values = []; }

  const token = ++_warnToken;
  try {
    const res = await fetch('/api/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ checks: [{ key: '_', pipeline, values }] }),
    });
    const data = await res.json();
    if (token !== _warnToken) return;  // superseded by a newer edit
    if (!res.ok) return;
    const result = (data.results || [])[0] || {};
    box.innerHTML = renderWarningsHtml(result.warnings);
  } catch {
    /* advisory only — never block the inspector on a failed fetch */
  }
}

function renderWarningsHtml(list) {
  if (!list || list.length === 0) return '';
  return list.map(w => {
    const level = w.level === 'error' ? 'error' : 'warn';
    const glyph = level === 'error' ? '✕' : '⚠';
    return `<div class="pipe-warn level-${level}">
      <span class="glyph">${glyph}</span>
      <span class="msg">${escapeHtml(w.message)}</span>
    </div>`;
  }).join('');
}

function renderAddMenu() {
  const autoSection = `
    <div class="add-scheme-section">Auto-discover · DFS over candidate feature pipelines</div>
    <div class="add-scheme-item auto-item" data-code="auto">
      <span class="code"><span class="auto-glyph">✦</span> auto</span>
      <span class="desc">search all valid pipelines (depth&nbsp;3) · pick smallest</span>
    </div>
  `;
  const sections = SCHEME_GROUPS.map(([title, codes]) => {
    const items = codes.map(code => {
      const info = SCHEME_INFO[code];
      const lossy = info.lossy ? '<span class="lossy-tag">lossy</span>' : '';
      return `<div class="add-scheme-item" data-code="${code}">
        <span class="code">${code}${lossy}</span>
        <span class="desc">${info.desc}</span>
      </div>`;
    }).join('');
    return `<div class="add-scheme-section">${title}</div>${items}`;
  }).join('');
  return `
    <details class="add-scheme">
      <summary>add</summary>
      <div class="add-scheme-menu">${autoSection}${sections}</div>
    </details>
  `;
}


// ─── run · /api/steps ─────────────────────────────────────────────

async function runSteps() {
  const text = document.getElementById('pgInput').value;
  const values = parseInput(text);

  if (!values.length) {
    toast('enter a sequence first', 'error');
    return;
  }
  if (!state.pipeline.length) {
    toast('pick at least one scheme', 'error');
    return;
  }

  updateStatus('RUNNING', `${values.length} values · ${state.pipeline.join('_')}`);

  try {
    const res = await fetch('/api/steps', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        values,
        pipeline: state.pipeline.length === 1 ? state.pipeline[0] : state.pipeline.join('_'),
        lossy: state.lossy,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `${res.status}`);
    renderSteps(data);
    renderDecodeSteps(data);
    showSection('section-steps');
    document.getElementById('section-steps').scrollIntoView({ behavior: 'smooth', block: 'start' });
    updateStatus('DONE', `${data.steps.length - 1} step${data.steps.length - 1 === 1 ? '' : 's'} · ${state.pipeline.join('_')}`);
  } catch (err) {
    console.error(err);
    updateStatus('ERROR', String(err.message || err).toLowerCase());
    toast(`run failed: ${err.message}`, 'error');
  }
}


// ─── step rendering ───────────────────────────────────────────────

function renderSteps(data) {
  const summary = document.getElementById('pgStepsSummary');
  const stepsEl = document.getElementById('pgSteps');

  const inputSize = data.steps[0].byte_size;
  const finalSize = data.steps[data.steps.length - 1].byte_size;
  const ratio = finalSize / Math.max(1, inputSize);
  const saved = (1 - ratio) * 100;
  const inputCount = Array.isArray(data.steps[0].output) ? data.steps[0].output.length : 1;

  let pipelineLabel;
  if (data.auto_origin === 'auto' && data.resolved_pipeline) {
    pipelineLabel = `<span class="auto-glyph">✦</span> auto resolved to <code class="hot">${escapeHtml(data.resolved_pipeline)}</code>`;
  } else if (data.resolved_pipeline) {
    pipelineLabel = `<code>${escapeHtml(data.resolved_pipeline)}</code>`;
  } else {
    pipelineLabel = `<em class="muted">no pipeline applied</em>`;
  }

  summary.innerHTML = `
    <div class="pg-summary-grid">
      <div class="pg-summary-block">
        <div class="out-label">Pipeline</div>
        <div class="pg-summary-pipeline">${pipelineLabel}</div>
      </div>
      <div class="pg-summary-block">
        <div class="out-label">Values</div>
        <div class="pg-summary-num">${inputCount.toLocaleString()}</div>
      </div>
      <div class="pg-summary-block">
        <div class="out-label">${inputSize}&nbsp;B → ${finalSize}&nbsp;B</div>
        <div class="pg-summary-num hot">${(saved >= 0 ? '−' : '+') + Math.abs(saved).toFixed(1)}%</div>
      </div>
    </div>
  `;

  stepsEl.innerHTML = '';

  data.steps.forEach((step, i) => {
    const card = document.createElement('article');
    card.className = `pg-step pg-step-${step.step}`;
    card.style.animationDelay = `${i * 80}ms`;

    const prevSize = i > 0 ? data.steps[i - 1].byte_size : step.byte_size;
    const delta = step.byte_size - prevSize;
    const deltaPct = prevSize > 0 ? (delta / prevSize) * 100 : 0;

    if (i === 0) {
      card.innerHTML = renderInputCard(step);
    } else {
      card.innerHTML = renderStepCard(step, i, prevSize, delta, deltaPct);
    }

    stepsEl.appendChild(card);

    // arrow connector between cards
    if (i < data.steps.length - 1) {
      const arrow = document.createElement('div');
      arrow.className = 'pg-step-arrow';
      arrow.style.animationDelay = `${i * 80 + 40}ms`;
      arrow.textContent = '↓';
      stepsEl.appendChild(arrow);
    }
  });

  // final wire-format triple — what `encode_feature_payload` would store
  if (data.steps.length > 1 && data.resolved_pipeline) {
    const lastStep = data.steps[data.steps.length - 1];
    const firstStep = data.steps[0];
    const finalArrow = document.createElement('div');
    finalArrow.className = 'pg-step-arrow';
    finalArrow.style.animationDelay = `${data.steps.length * 80 + 40}ms`;
    finalArrow.textContent = '↓';
    stepsEl.appendChild(finalArrow);

    const finalCard = document.createElement('article');
    finalCard.className = 'pg-step pg-final-triple';
    finalCard.style.animationDelay = `${data.steps.length * 80 + 80}ms`;
    finalCard.innerHTML = renderFinalTriple(lastStep, firstStep, data);
    stepsEl.appendChild(finalCard);
  }
}

function renderFinalTriple(lastStep, firstStep, data) {
  const value = lastStep.output;
  const scheme = data.resolved_pipeline;
  const aux = lastStep.cumulative_aux || {};
  const auxEntries = Object.entries(aux);

  // Byte cost of each component, computed identically to encode_feature
  // (compact JSON with separators=(',',':')).
  const valueBytes = compactJsonSize(value);
  const schemeBytes = compactJsonSize(scheme) + 1; // +1 for the comma separator
  const auxBytes = auxEntries.length > 0 ? compactJsonSize(aux) + 1 : 0;
  // brackets + commas overhead
  const totalBytes = lastStep.byte_size;
  const overhead = totalBytes - valueBytes - schemeBytes - auxBytes;

  // Uncompressed payload: encode_feature_payload would store [values] with no scheme/aux
  const uncompressedValues = firstStep.output;
  const uncompressedBytes = firstStep.byte_size;
  const savedBytes = uncompressedBytes - totalBytes;
  const savedPct = uncompressedBytes > 0 ? (savedBytes / uncompressedBytes) * 100 : 0;
  const uncompressedPreview = `<pre class="wire-triple-pre">${escapeHtml(formatTripleValue(uncompressedValues))}</pre>`;

  const valuePreview = `<pre class="wire-triple-pre">${escapeHtml(formatTripleValue(value))}</pre>`;
  const auxPretty = auxEntries.length === 0
    ? '<em class="muted">{ }  ·  no aux for this scheme</em>'
    : `<pre class="wire-triple-pre">${escapeHtml(JSON.stringify(aux, null, 2))}</pre>`;

  // Visual proportion bar showing where the bytes go.
  const segments = [
    { label: 'value',  bytes: Math.max(0, valueBytes),  cls: 'seg-value' },
    { label: 'scheme', bytes: Math.max(0, schemeBytes), cls: 'seg-scheme' },
    { label: 'aux',    bytes: Math.max(0, auxBytes),    cls: 'seg-aux' },
  ];
  if (overhead > 0) segments.push({ label: 'overhead', bytes: overhead, cls: 'seg-overhead' });
  const segMax = totalBytes || 1;

  // Legend ABOVE the bar — labels are always readable regardless of segment
  // width. The bar below is purely a proportional colour strip.
  const legendHtml = segments.map(s => {
    const pct = (s.bytes / segMax) * 100;
    return `<div class="pg-byte-bar-item">
      <span class="swatch ${s.cls}"></span>
      <span class="label">${s.label}</span>
      <span class="bytes">${s.bytes} B</span>
      <span class="pct">${pct.toFixed(1)}%</span>
    </div>`;
  }).join('');

  const segHtml = segments.map(s => {
    const pct = (s.bytes / segMax) * 100;
    return `<div class="pg-byte-bar-seg ${s.cls}" style="flex: ${Math.max(0.5, pct).toFixed(2)};" title="${s.label}: ${s.bytes} B (${pct.toFixed(1)}%)"></div>`;
  }).join('');

  const savedClass = savedBytes > 0 ? 'shrunk' : (savedBytes < 0 ? 'grew' : '');
  const savedLabel = savedBytes === 0
    ? '±0 B'
    : `${savedBytes > 0 ? '−' : '+'}${Math.abs(savedBytes)} B · ${(savedPct >= 0 ? '−' : '+') + Math.abs(savedPct).toFixed(1)}%`;

  return `
    <header class="pg-step-head">
      <div class="pg-step-num">§ ∎</div>
      <div>
        <h3 class="pg-step-title">
          <span class="auto-glyph">⊡</span>
          <span class="pg-step-name">Final encoded entry</span>
        </h3>
        <p class="pg-step-desc">
          What <code>encode_feature_payload</code> serialises with
          <code>json.dumps([value, scheme, aux])</code>. Total bytes account
          for all three components plus separators.
        </p>
      </div>
      <div class="pg-step-size shrunk">
        <span class="pg-step-size-num">${totalBytes}</span><span class="pg-step-size-unit">B</span>
        <span class="pg-step-size-delta">final · ${scheme}</span>
      </div>
    </header>
    <div class="pg-step-body">
      <div class="pg-block">
        <div class="pg-block-label">BYTE BREAKDOWN <span class="muted">where each byte goes</span></div>
        <div class="pg-byte-bar">
          <div class="pg-byte-bar-legend">${legendHtml}</div>
          <div class="pg-byte-bar-track">${segHtml}</div>
        </div>
      </div>
      <div class="wire-triple-grid">
        <div class="wire-triple-cell">
          <div class="wire-triple-label">[0] value · ${valueBytes} B</div>
          ${valuePreview}
        </div>
        <div class="wire-triple-cell">
          <div class="wire-triple-label">[1] scheme · ${schemeBytes} B</div>
          <pre class="wire-triple-pre wire-triple-scheme">${escapeHtml(JSON.stringify(scheme))}</pre>
        </div>
        <div class="wire-triple-cell">
          <div class="wire-triple-label">[2] aux · ${auxBytes} B</div>
          ${auxPretty}
        </div>
      </div>

      <div class="pg-payload-compare">
        <div class="pg-payload-compare-head">
          <span class="pg-payload-compare-title">PAYLOAD COMPARISON</span>
          <span class="pg-payload-compare-meta muted">as stored by <code>encode_feature_payload</code></span>
        </div>
        <div class="pg-payload-compare-grid">
          <div class="pg-payload-compare-cell pg-payload-uncompressed">
            <div class="pg-payload-cell-label">
              uncompressed
              <span class="pg-payload-cell-bytes">${uncompressedBytes} B</span>
            </div>
            <div class="pg-payload-cell-note muted">json.dumps([values])</div>
            ${uncompressedPreview}
          </div>
          <div class="pg-payload-compare-arrow">→</div>
          <div class="pg-payload-compare-cell pg-payload-compressed">
            <div class="pg-payload-cell-label">
              compressed
              <span class="pg-payload-cell-bytes hot">${totalBytes} B</span>
            </div>
            <div class="pg-payload-cell-note muted">json.dumps([value, scheme, aux])</div>
            <pre class="wire-triple-pre">${escapeHtml(formatCompressedTriple(value, scheme, aux))}</pre>
          </div>
          <div class="pg-payload-compare-savings ${savedClass}">
            <div class="pg-payload-savings-num">${savedLabel}</div>
            <div class="pg-payload-savings-sub muted">bytes saved</div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function formatCompressedTriple(value, scheme, aux) {
  const triple = Object.keys(aux).length > 0 ? [value, scheme, aux] : [value, scheme];
  const json = JSON.stringify(triple);
  if (json.length <= 200) return json;
  return json.slice(0, 200) + '…';
}

function compactJsonSize(value) {
  try {
    return new Blob([JSON.stringify(value)]).size;
  } catch {
    return 0;
  }
}

function renderInputCard(step) {
  const out = step.output;
  return `
    <header class="pg-step-head">
      <div class="pg-step-num">§ 00.</div>
      <div>
        <h3 class="pg-step-title">Input</h3>
        <p class="pg-step-desc">${escapeHtml(step.description)}</p>
      </div>
      <div class="pg-step-size"><span class="pg-step-size-num">${step.byte_size}</span><span class="pg-step-size-unit">B</span></div>
    </header>
    <div class="pg-step-body">
      ${renderValueBlock(out, 'INPUT')}
    </div>
  `;
}

function renderStepCard(step, idx, prevSize, delta, deltaPct) {
  const sizeClass = delta < 0 ? 'shrunk' : (delta > 0 ? 'grew' : '');
  const deltaLabel = delta === 0
    ? '±0 B'
    : `${delta > 0 ? '+' : '−'}${Math.abs(delta)} B · ${(deltaPct >= 0 ? '+' : '−')}${Math.abs(deltaPct).toFixed(1)}%`;

  return `
    <header class="pg-step-head">
      <div class="pg-step-num">§ ${String(idx).padStart(2, '0')}.</div>
      <div>
        <h3 class="pg-step-title">
          <code class="pg-step-code">${escapeHtml(step.step)}</code>
          <span class="pg-step-name">${escapeHtml(step.name)}</span>
        </h3>
        <p class="pg-step-desc">${escapeHtml(step.description)}</p>
      </div>
      <div class="pg-step-size ${sizeClass}">
        <span class="pg-step-size-num">${step.byte_size}</span><span class="pg-step-size-unit">B</span>
        <span class="pg-step-size-delta">${deltaLabel}</span>
      </div>
    </header>
    <div class="pg-step-body">
      ${renderSchemeVisual(step)}
    </div>
  `;
}

// ─── per-scheme visualisations ──────────────────────────────────

function renderSchemeVisual(step) {
  switch (step.step) {
    case 'cat':   return renderCatVisual(step);
    case 'rle':   return renderRleVisual(step);
    case 'del':   return renderDelVisual(step);
    case 'quant': return renderQuantVisual(step);
    case 'stl':   return renderStlVisual(step);
    case 'tbqm':
    case 'tbqp':  return renderTbqVisual(step);
    case 'bp':
    case 'bm':
    case 'nbp':   return renderPackVisual(step);
    default:      return renderGenericVisual(step);
  }
}

function renderGenericVisual(step) {
  return `
    ${renderValueBlock(step.input, 'INPUT')}
    ${renderValueBlock(step.output, 'OUTPUT')}
    ${renderAuxBlock(step.aux)}
  `;
}

function renderCatVisual(step) {
  const stoi = step.aux.stoi || {};
  const entries = Object.entries(stoi).sort((a, b) => a[1] - b[1]);
  const dictRows = entries.map(([k, v]) => {
    const occ = step.input.filter(x => String(x) === String(k)).length;
    return `<div class="pg-dict-row">
      <span class="pg-dict-key">${formatScalar(k)}</span>
      <span class="pg-dict-arrow">→</span>
      <span class="pg-dict-val">${v}</span>
      <span class="pg-dict-occ">×${occ}</span>
    </div>`;
  }).join('');

  return `
    ${renderValueBlock(step.input, 'INPUT')}
    <div class="pg-block">
      <div class="pg-block-label">DICTIONARY <span class="muted">stoi · most frequent → 0</span></div>
      <div class="pg-dict">${dictRows}</div>
    </div>
    ${renderValueBlock(step.output, 'OUTPUT', { mapWith: stoi })}
  `;
}

function renderRleVisual(step) {
  const input = step.input || [];
  // detect runs in the input for highlighting
  const runs = [];
  let i = 0;
  while (i < input.length) {
    let j = i;
    while (j < input.length && input[j] === input[i]) j++;
    runs.push({ value: input[i], count: j - i, start: i, end: j - 1 });
    i = j;
  }

  const inputHtml = runs.map((r, idx) => {
    const cls = `pg-run pg-run-${idx % 4}`;
    const items = Array.from({ length: r.count }, () => formatScalar(r.value)).join(', ');
    return `<span class="${cls}" title="run of ${r.count}">${escapeHtml(items)}</span>`;
  }).join('<span class="pg-run-sep">,&nbsp;</span>');

  const outPairs = [];
  const out = step.output || [];
  for (let k = 0; k < out.length; k += 2) {
    outPairs.push(`[<span class="pg-pair-v">${formatScalar(out[k])}</span>, <span class="pg-pair-n">${formatScalar(out[k+1])}</span>]`);
  }

  return `
    <div class="pg-block">
      <div class="pg-block-label">INPUT <span class="muted">runs highlighted</span></div>
      <div class="pg-values">[${inputHtml}]</div>
      <div class="pg-meta">${input.length} values · ${runs.length} run${runs.length === 1 ? '' : 's'}</div>
    </div>
    <div class="pg-block">
      <div class="pg-block-label">OUTPUT <span class="muted">[value, count] pairs flattened</span></div>
      <div class="pg-values">[${outPairs.join(', ')}]</div>
      <div class="pg-meta">${out.length} values</div>
    </div>
  `;
}

function renderDelVisual(step) {
  const input = step.input || [];
  const output = step.output || [];
  const v0 = step.aux.v0;

  const pairs = output.map((d, k) => {
    const a = input[k];
    const b = input[k + 1];
    return `<div class="pg-delta-row">
      <span class="pg-delta-pair">${formatScalar(a)} → ${formatScalar(b)}</span>
      <span class="pg-delta-arrow">=</span>
      <span class="pg-delta-val ${d < 0 ? 'neg' : ''}">${d >= 0 ? '+' : ''}${d}</span>
    </div>`;
  }).join('');

  return `
    ${renderValueBlock(input, 'INPUT')}
    <div class="pg-block">
      <div class="pg-block-label">DELTAS <span class="muted">v[i+1] − v[i]</span></div>
      <div class="pg-delta-list">${pairs}</div>
    </div>
    ${renderValueBlock(output, 'OUTPUT')}
    <div class="pg-block">
      <div class="pg-block-label">AUX <span class="muted">stored separately for decoding</span></div>
      <div class="pg-aux">v0 = <code>${formatScalar(v0)}</code></div>
    </div>
  `;
}


function renderQuantVisual(step) {
  const aux = step.aux || {};
  return `
    ${renderValueBlock(step.input, 'INPUT')}
    <div class="pg-block">
      <div class="pg-block-label">QUANTISATION <span class="muted">${aux.q_sym ? 'symmetric' : 'asymmetric'} · ${aux.q_bits || 8}-bit</span></div>
      <div class="pg-aux pg-quant-aux">
        <div>scale = <code>${formatScalar(aux.q_scale)}</code></div>
        <div>zero_point = <code>${formatScalar(aux.q_zp)}</code></div>
        <div class="muted">⚠ lossy — see decode step for precision-loss metrics</div>
      </div>
    </div>
    ${renderValueBlock(step.output, 'OUTPUT')}
  `;
}

function renderQuantLoss(step) {
  const loss = step.loss_metrics;
  if (!loss) return '';

  const cells = [
    { label: 'MAE',      value: formatLossNum(loss.mae),         sub: 'mean absolute error' },
    { label: 'Max AE',   value: formatLossNum(loss.max_ae),      sub: 'worst single value' },
    { label: 'RMSE',     value: formatLossNum(loss.rmse),        sub: 'root mean squared' },
    { label: 'MRE',      value: formatPercent(loss.mre),         sub: 'mean relative' },
    { label: 'SNR',      value: formatSnr(loss.snr_db) + ' dB',  sub: 'signal-to-noise' },
    { label: 'Cos Sim',  value: formatCosine(loss.cosine_sim),   sub: 'angular alignment' },
  ];

  const cellHtml = cells.map(c => `
    <div class="pg-loss-cell">
      <div class="pg-loss-label">${c.label}</div>
      <div class="pg-loss-val">${c.value}</div>
      <div class="pg-loss-sub">${c.sub}</div>
    </div>
  `).join('');

  // sample value-by-value reconstruction for the first few entries.
  // On a decode step `step.input` is uint8 codes, not floats, so the
  // server attaches `original_sample` (the floats that were fed to
  // quant during encoding) explicitly.
  const recon = step.reconstructed_sample || [];
  const originals = step.original_sample || step.input || [];
  const original = originals.slice(0, recon.length);
  const sampleRows = original.map((o, i) => {
    const r = recon[i];
    const err = (typeof o === 'number' && typeof r === 'number') ? Math.abs(o - r) : null;
    return `<div class="pg-loss-sample-row">
      <span class="pg-loss-sample-orig">${formatScalar(o)}</span>
      <span class="pg-loss-sample-arrow">→</span>
      <span class="pg-loss-sample-recon">${formatScalar(r)}</span>
      <span class="pg-loss-sample-err">${err !== null ? '±' + formatLossNum(err) : ''}</span>
    </div>`;
  }).join('');

  return `
    <div class="pg-block">
      <div class="pg-block-label">INFORMATION LOSS <span class="muted">round-trip error vs original floats</span></div>
      <div class="pg-loss-grid">${cellHtml}</div>
      ${sampleRows ? `
        <div class="pg-loss-sample">
          <div class="pg-loss-sample-head">
            <span>ORIGINAL</span><span></span><span>RECONSTRUCTED</span><span>|Δ|</span>
          </div>
          ${sampleRows}
        </div>
      ` : ''}
    </div>
  `;
}

function formatLossNum(v) {
  if (v == null) return '—';
  if (v === 0) return '0';
  const abs = Math.abs(v);
  if (abs >= 100)   return v.toFixed(2);
  if (abs >= 1)     return v.toFixed(4);
  if (abs >= 0.001) return v.toFixed(5);
  return v.toExponential(2);
}

function formatPercent(v) {
  if (v == null) return '—';
  const pct = v * 100;
  if (pct === 0) return '0%';
  if (Math.abs(pct) >= 1)    return pct.toFixed(2) + '%';
  if (Math.abs(pct) >= 0.01) return pct.toFixed(3) + '%';
  return pct.toExponential(2) + '%';
}

function formatSnr(v) {
  if (v == null) return '∞';
  if (!isFinite(v)) return '∞';
  return v.toFixed(1);
}

function formatCosine(v) {
  if (v == null) return '—';
  // values typically very close to 1 — show enough digits to make differences visible
  if (v >= 0.99999) return v.toFixed(7);
  if (v >= 0.999)   return v.toFixed(6);
  if (v >= 0.99)    return v.toFixed(5);
  return v.toFixed(4);
}

function renderStlVisual(step) {
  const sntRanges = step.aux.snt_ranges || {};
  const totalSentinels = Object.values(sntRanges)
    .reduce((sum, ranges) => sum + ranges.reduce((s, r) => s + (r.length === 1 ? 1 : r[1] - r[0] + 1), 0), 0);
  const ranges = Object.entries(sntRanges).map(([v, ranges]) =>
    `<div class="pg-stl-row">
      <span class="pg-stl-val">${formatScalar(v)}</span>
      <span class="pg-stl-arrow">at</span>
      <span class="pg-stl-pos">${ranges.map(r => r.length === 1 ? `[${r[0]}]` : `[${r[0]}…${r[1]}]`).join(', ')}</span>
    </div>`
  ).join('');

  return `
    ${renderValueBlock(step.input, 'INPUT')}
    <div class="pg-block">
      <div class="pg-block-label">SENTINELS REMOVED <span class="muted">${totalSentinels} outlier${totalSentinels === 1 ? '' : 's'} · iqr × 3</span></div>
      <div class="pg-stl">${ranges || '<em class="muted">no outliers detected</em>'}</div>
    </div>
    ${renderValueBlock(step.output, 'OUTPUT')}
  `;
}

function renderPackVisual(step) {
  const out = step.output;
  const bytes = decodeBase64Bytes(typeof out === 'string' ? out : '');
  const inputLen = Array.isArray(step.input) ? step.input.length : 1;

  // `bytes` is a Uint8Array — its `.map()` returns another Uint8Array, NOT
  // an Array of strings. Coerce to a plain Array first so the hex template
  // strings actually survive the map.
  const hexCells = Array.from(bytes.slice(0, 64)).map((b, i) => {
    const byteCls = i < 4 ? 'pg-byte-header' : 'pg-byte-payload';
    return `<span class="pg-byte ${byteCls}" title="byte ${i}: 0x${b.toString(16).padStart(2,'0')} = ${b}">${b.toString(16).padStart(2, '0')}</span>`;
  }).join('');
  const more = bytes.length > 64 ? `<span class="pg-byte-more">+${bytes.length - 64} more bytes</span>` : '';

  return `
    ${renderValueBlock(step.input, 'INPUT')}
    <div class="pg-block">
      <div class="pg-block-label">PACKED BYTES <span class="muted">first bytes are header · ${bytes.length} total</span></div>
      <div class="pg-bytes">${hexCells}${more}</div>
    </div>
    <div class="pg-block">
      <div class="pg-block-label">BASE-64 OUTPUT</div>
      <div class="pg-base64">${escapeHtml(typeof out === 'string' ? out : JSON.stringify(out))}</div>
      <div class="pg-meta">${inputLen} input value${inputLen === 1 ? '' : 's'} → ${bytes.length} byte${bytes.length === 1 ? '' : 's'} → ${typeof out === 'string' ? out.length : 0} base-64 chars</div>
    </div>
  `;
}

// ─── decode walk-back rendering ────────────────────────────────────

function renderDecodeSteps(data) {
  const wrap = document.getElementById('pgDecodeSteps');
  const section = document.getElementById('section-decode');
  if (!wrap || !section) return;

  const decodeSteps = data.decode_steps || [];
  if (decodeSteps.length === 0) {
    section.classList.add('hidden');
    wrap.innerHTML = '';
    return;
  }
  showSection('section-decode');

  wrap.innerHTML = '';
  decodeSteps.forEach((step, i) => {
    const card = document.createElement('article');
    card.className = `pg-step pg-step-${step.step} pg-decode-step`;
    card.style.animationDelay = `${i * 80}ms`;

    if (i === 0) {
      card.innerHTML = renderDecodeStartCard(step);
    } else {
      card.innerHTML = renderDecodeStepCard(step, i, decodeSteps.length - 1);
    }
    wrap.appendChild(card);

    if (i < decodeSteps.length - 1) {
      const arrow = document.createElement('div');
      arrow.className = 'pg-step-arrow';
      arrow.style.animationDelay = `${i * 80 + 40}ms`;
      arrow.textContent = '↑';
      wrap.appendChild(arrow);
    }
  });
}

function renderDecodeStartCard(step) {
  return `
    <header class="pg-step-head">
      <div class="pg-step-num">§ ∎</div>
      <div>
        <h3 class="pg-step-title">${escapeHtml(step.name)}</h3>
        <p class="pg-step-desc">${escapeHtml(step.description)}</p>
      </div>
      <div class="pg-step-size"><span class="pg-step-size-num">${step.byte_size}</span><span class="pg-step-size-unit">B</span></div>
    </header>
    <div class="pg-step-body">
      ${renderValueBlock(step.output, 'ENCODED VALUE')}
    </div>
  `;
}

function renderDecodeStepCard(step, idx, total) {
  if (step.error) {
    return `
      <header class="pg-step-head">
        <div class="pg-step-num">§ ${String(idx).padStart(2, '0')}.</div>
        <div>
          <h3 class="pg-step-title">
            <code class="pg-step-code">${escapeHtml(step.step)}</code>
            <span class="pg-step-name">${escapeHtml(step.name)}</span>
            <span class="muted">· decode</span>
          </h3>
          <p class="pg-step-desc">${escapeHtml(step.description)}</p>
        </div>
      </header>
      <div class="pg-step-body">
        <div class="pg-block"><div class="pg-block-label">ERROR</div><div class="pg-values">${escapeHtml(step.error)}</div></div>
      </div>
    `;
  }
  return `
    <header class="pg-step-head">
      <div class="pg-step-num">§ ${String(idx).padStart(2, '0')}.</div>
      <div>
        <h3 class="pg-step-title">
          <code class="pg-step-code">${escapeHtml(step.step)}</code>
          <span class="pg-step-name">${escapeHtml(step.name)}</span>
          <span class="muted">· decode${idx === total ? ' · final' : ''}</span>
        </h3>
        <p class="pg-step-desc">${escapeHtml(step.description)}</p>
      </div>
      <div class="pg-step-size">
        <span class="pg-step-size-num">${step.byte_size}</span><span class="pg-step-size-unit">B</span>
      </div>
    </header>
    <div class="pg-step-body">
      ${renderDecodeSchemeVisual(step)}
    </div>
  `;
}

function renderDecodeSchemeVisual(step) {
  switch (step.step) {
    case 'cat':   return renderCatDecodeVisual(step);
    case 'rle':   return renderRleDecodeVisual(step);
    case 'del':   return renderDelDecodeVisual(step);
    case 'quant': return renderQuantDecodeVisual(step);
    case 'stl':   return renderStlDecodeVisual(step);
    case 'tbqm':
    case 'tbqp':  return renderTbqDecodeVisual(step);
    case 'bp':
    case 'bm':
    case 'nbp':   return renderPackDecodeVisual(step);
    default:      return renderGenericDecodeVisual(step);
  }
}

function renderGenericDecodeVisual(step) {
  return `
    ${renderValueBlock(step.input, 'ENCODED')}
    ${renderDecodeAuxBlock(step.aux_used)}
    ${renderValueBlock(step.output, 'DECODED')}
  `;
}

function renderDecodeAuxBlock(aux) {
  if (!aux || Object.keys(aux).length === 0) {
    return `
      <div class="pg-block">
        <div class="pg-block-label">AUX CONSUMED</div>
        <div class="pg-aux"><em class="muted">none — decode is parameter-free</em></div>
      </div>
    `;
  }
  const entries = Object.entries(aux).map(([k, v]) =>
    `<div class="pg-aux-row"><span class="pg-aux-key">${escapeHtml(k)}</span> = <code>${escapeHtml(JSON.stringify(v))}</code></div>`
  ).join('');
  return `
    <div class="pg-block">
      <div class="pg-block-label">AUX CONSUMED <span class="muted">read from the wire-format triple</span></div>
      <div class="pg-aux">${entries}</div>
    </div>
  `;
}

function renderCatDecodeVisual(step) {
  const stoi = (step.aux_used && step.aux_used.stoi) || {};
  // itos is the inverse mapping that decode actually uses
  const itos = {};
  Object.entries(stoi).forEach(([k, v]) => { itos[v] = k; });
  const entries = Object.entries(itos).sort((a, b) => Number(a[0]) - Number(b[0]));
  const dictRows = entries.map(([v, k]) => {
    const occ = (step.input || []).filter(x => Number(x) === Number(v)).length;
    return `<div class="pg-dict-row">
      <span class="pg-dict-val">${v}</span>
      <span class="pg-dict-arrow">→</span>
      <span class="pg-dict-key">${formatScalar(k)}</span>
      <span class="pg-dict-occ">×${occ}</span>
    </div>`;
  }).join('');

  return `
    ${renderValueBlock(step.input, 'ENCODED · ids', { mapWith: itos })}
    <div class="pg-block">
      <div class="pg-block-label">DICTIONARY <span class="muted">itos · inverse of stoi</span></div>
      <div class="pg-dict">${dictRows}</div>
    </div>
    ${renderValueBlock(step.output, 'DECODED · strings')}
  `;
}

function renderRleDecodeVisual(step) {
  const input = step.input || [];
  const inPairs = [];
  for (let k = 0; k < input.length; k += 2) {
    inPairs.push(`[<span class="pg-pair-v">${formatScalar(input[k])}</span>, <span class="pg-pair-n">${formatScalar(input[k+1])}</span>]`);
  }

  // detect runs in the OUTPUT for highlighting expansion
  const output = step.output || [];
  const runs = [];
  let i = 0;
  while (i < output.length) {
    let j = i;
    while (j < output.length && output[j] === output[i]) j++;
    runs.push({ value: output[i], count: j - i });
    i = j;
  }
  const outHtml = runs.map((r, idx) => {
    const cls = `pg-run pg-run-${idx % 4}`;
    const items = Array.from({ length: r.count }, () => formatScalar(r.value)).join(', ');
    return `<span class="${cls}" title="expanded to ${r.count}">${escapeHtml(items)}</span>`;
  }).join('<span class="pg-run-sep">,&nbsp;</span>');

  return `
    <div class="pg-block">
      <div class="pg-block-label">ENCODED <span class="muted">[value, count] pairs</span></div>
      <div class="pg-values">[${inPairs.join(', ')}]</div>
      <div class="pg-meta">${input.length} values · ${inPairs.length} pair${inPairs.length === 1 ? '' : 's'}</div>
    </div>
    <div class="pg-block">
      <div class="pg-block-label">DECODED <span class="muted">each pair expanded</span></div>
      <div class="pg-values">[${outHtml}]</div>
      <div class="pg-meta">${output.length} values · ${runs.length} run${runs.length === 1 ? '' : 's'}</div>
    </div>
  `;
}

function renderDelDecodeVisual(step) {
  const input = step.input || [];
  const output = step.output || [];
  const v0 = step.aux_used && step.aux_used.v0;

  // running cumulative sum walkthrough
  const rows = input.map((d, k) => {
    const prev = output[k];
    const next = output[k + 1];
    return `<div class="pg-delta-row">
      <span class="pg-delta-pair">${formatScalar(prev)} + ${d >= 0 ? '+' : ''}${d}</span>
      <span class="pg-delta-arrow">=</span>
      <span class="pg-delta-val">${formatScalar(next)}</span>
    </div>`;
  }).join('');

  return `
    ${renderValueBlock(input, 'ENCODED · deltas')}
    <div class="pg-block">
      <div class="pg-block-label">AUX CONSUMED <span class="muted">seed value</span></div>
      <div class="pg-aux">v0 = <code>${formatScalar(v0)}</code></div>
    </div>
    <div class="pg-block">
      <div class="pg-block-label">CUMULATIVE SUM <span class="muted">v[i+1] = v[i] + Δ[i]</span></div>
      <div class="pg-delta-list">${rows}</div>
    </div>
    ${renderValueBlock(output, 'DECODED')}
  `;
}

function renderQuantDecodeVisual(step) {
  const aux = step.aux_used || {};
  return `
    ${renderValueBlock(step.input, 'ENCODED · uint8 codes')}
    <div class="pg-block">
      <div class="pg-block-label">DEQUANTISATION <span class="muted">value ≈ (code − zp) × scale</span></div>
      <div class="pg-aux pg-quant-aux">
        <div>scale = <code>${formatScalar(aux.q_scale)}</code></div>
        <div>zero_point = <code>${formatScalar(aux.q_zp)}</code></div>
        <div class="muted">⚠ lossy — values are approximations of the originals</div>
      </div>
    </div>
    ${renderValueBlock(step.output, 'DECODED · reconstructed floats')}
    ${renderQuantLoss(step)}
  `;
}

function renderTbqVisual(step) {
  const aux = step.aux || {};
  const isProd = step.step === 'tbqp';
  const dim = aux.tq_dim || '?';
  const bits = aux.tq_bits || 4;
  const norm = aux.tq_norm != null ? formatScalar(aux.tq_norm) : '?';
  const prodExtra = isProd
    ? `<div>residual_norm = <code>${formatScalar(aux.tq_rnorm)}</code></div>
       <div>qjl_seed = <code>${aux.tq_qseed}</code></div>`
    : '';
  return `
    ${renderValueBlock(step.input, 'INPUT · float vector')}
    <div class="pg-block">
      <div class="pg-block-label">TURBOQUANT ${isProd ? 'PROD' : 'MSE'} <span class="muted">${dim}-dim · ${bits}-bit${isProd ? ' MSE + 1-bit QJL residual' : ''} · lossy</span></div>
      <div class="pg-aux pg-quant-aux">
        <div>dim = <code>${dim}</code></div>
        <div>bits = <code>${bits}</code></div>
        <div>seed = <code>${aux.tq_seed != null ? aux.tq_seed : '?'}</code></div>
        <div>norm = <code>${norm}</code></div>
        ${prodExtra}
        <div class="muted">⚠ lossy — see decode step for precision-loss metrics</div>
      </div>
    </div>
    <div class="pg-block">
      <div class="pg-block-label">OUTPUT <span class="muted">base64 bitstream (no downstream packing needed)</span></div>
      <div class="pg-base64">${escapeHtml(typeof step.output === 'string' ? step.output.slice(0, 80) + (step.output.length > 80 ? '…' : '') : JSON.stringify(step.output))}</div>
      <div class="pg-meta">${typeof step.output === 'string' ? step.output.length : 0} base64 chars</div>
    </div>
  `;
}

function renderTbqDecodeVisual(step) {
  const aux = step.aux_used || {};
  const isProd = step.step === 'tbqp';
  const inp = step.input;
  const bytes = decodeBase64Bytes(typeof inp === 'string' ? inp : '');
  const prodExtra = isProd
    ? `<div>tq_rnorm = <code>${formatScalar(aux.tq_rnorm)}</code></div>
       <div>tq_qseed = <code>${aux.tq_qseed}</code></div>`
    : '';
  return `
    <div class="pg-block">
      <div class="pg-block-label">BASE-64 INPUT <span class="muted">${bytes.length} bytes · ${isProd ? 'mse_indices + qjl_signs + residual_norm' : 'mse_indices'}</span></div>
      <div class="pg-base64">${escapeHtml(typeof inp === 'string' ? inp.slice(0, 80) + (inp.length > 80 ? '…' : '') : JSON.stringify(inp))}</div>
    </div>
    <div class="pg-block">
      <div class="pg-block-label">AUX CONSUMED <span class="muted">decoding parameters</span></div>
      <div class="pg-aux pg-quant-aux">
        <div>tq_dim = <code>${aux.tq_dim}</code></div>
        <div>tq_bits = <code>${aux.tq_bits}</code></div>
        <div>tq_seed = <code>${aux.tq_seed}</code></div>
        <div>tq_norm = <code>${formatScalar(aux.tq_norm)}</code></div>
        ${prodExtra}
        <div class="muted">⚠ lossy — values are approximations of the originals</div>
      </div>
    </div>
    ${renderValueBlock(step.output, 'DECODED · reconstructed floats')}
    ${renderQuantLoss(step)}
  `;
}

function renderStlDecodeVisual(step) {
  const sntRanges = (step.aux_used && step.aux_used.snt_ranges) || {};
  const totalSentinels = Object.values(sntRanges)
    .reduce((sum, ranges) => sum + ranges.reduce((s, r) => s + (r.length === 1 ? 1 : r[1] - r[0] + 1), 0), 0);
  const ranges = Object.entries(sntRanges).map(([v, ranges]) =>
    `<div class="pg-stl-row">
      <span class="pg-stl-val">${formatScalar(v)}</span>
      <span class="pg-stl-arrow">spliced at</span>
      <span class="pg-stl-pos">${ranges.map(r => r.length === 1 ? `[${r[0]}]` : `[${r[0]}…${r[1]}]`).join(', ')}</span>
    </div>`
  ).join('');

  return `
    ${renderValueBlock(step.input, 'ENCODED · non-sentinel values')}
    <div class="pg-block">
      <div class="pg-block-label">SENTINELS RESTORED <span class="muted">${totalSentinels} value${totalSentinels === 1 ? '' : 's'} re-inserted</span></div>
      <div class="pg-stl">${ranges || '<em class="muted">no sentinels stored</em>'}</div>
    </div>
    ${renderValueBlock(step.output, 'DECODED')}
  `;
}

function renderPackDecodeVisual(step) {
  const inp = step.input;
  const bytes = decodeBase64Bytes(typeof inp === 'string' ? inp : '');
  const outLen = Array.isArray(step.output) ? step.output.length : 1;

  const hexCells = Array.from(bytes.slice(0, 64)).map((b, i) => {
    const byteCls = i < 4 ? 'pg-byte-header' : 'pg-byte-payload';
    return `<span class="pg-byte ${byteCls}" title="byte ${i}: 0x${b.toString(16).padStart(2,'0')} = ${b}">${b.toString(16).padStart(2, '0')}</span>`;
  }).join('');
  const more = bytes.length > 64 ? `<span class="pg-byte-more">+${bytes.length - 64} more bytes</span>` : '';

  return `
    <div class="pg-block">
      <div class="pg-block-label">BASE-64 INPUT</div>
      <div class="pg-base64">${escapeHtml(typeof inp === 'string' ? inp : JSON.stringify(inp))}</div>
      <div class="pg-meta">${typeof inp === 'string' ? inp.length : 0} base-64 chars → ${bytes.length} byte${bytes.length === 1 ? '' : 's'} → ${outLen} value${outLen === 1 ? '' : 's'}</div>
    </div>
    <div class="pg-block">
      <div class="pg-block-label">PACKED BYTES <span class="muted">first bytes are header · ${bytes.length} total</span></div>
      <div class="pg-bytes">${hexCells}${more}</div>
    </div>
    ${renderValueBlock(step.output, 'DECODED')}
  `;
}

function decodeBase64Bytes(b64) {
  if (!b64) return new Uint8Array(0);
  try {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  } catch {
    return new Uint8Array(0);
  }
}

// ─── shared blocks ────────────────────────────────────────────────

function renderValueBlock(value, label, opts = {}) {
  const len = Array.isArray(value) ? value.length : 1;
  const formatted = formatValueList(value, opts);
  return `
    <div class="pg-block">
      <div class="pg-block-label">${escapeHtml(label)}</div>
      <div class="pg-values">${formatted}</div>
      <div class="pg-meta">${len} value${len === 1 ? '' : 's'}</div>
    </div>
  `;
}

function renderAuxBlock(aux) {
  if (!aux || Object.keys(aux).length === 0) return '';
  const entries = Object.entries(aux).map(([k, v]) =>
    `<div class="pg-aux-row"><span class="pg-aux-key">${escapeHtml(k)}</span> = <code>${escapeHtml(JSON.stringify(v))}</code></div>`
  ).join('');
  return `
    <div class="pg-block">
      <div class="pg-block-label">AUX <span class="muted">stored separately</span></div>
      <div class="pg-aux">${entries}</div>
    </div>
  `;
}

function formatValueList(value, opts = {}) {
  if (typeof value === 'string') {
    if (value.length > 200) {
      return `<span class="pg-str">${escapeHtml(value.slice(0, 180))}<span class="muted">…+${value.length - 180}</span></span>`;
    }
    return `<span class="pg-str">"${escapeHtml(value)}"</span>`;
  }
  if (!Array.isArray(value)) return formatScalar(value);

  const limit = 80;
  const display = value.slice(0, limit);
  const cells = display.map(v => {
    if (opts.mapWith && Object.prototype.hasOwnProperty.call(opts.mapWith, String(v))) {
      return `<span class="pg-cell pg-cell-mapped" title="${escapeAttr(opts.mapWith[String(v)] + ' ← ' + v)}">${formatScalar(v)}</span>`;
    }
    return `<span class="pg-cell">${formatScalar(v)}</span>`;
  });
  const more = value.length > limit ? `<span class="pg-cell pg-cell-more">+${value.length - limit}</span>` : '';
  return `[<span class="pg-cells">${cells.join(', ')}${more}</span>]`;
}

function formatScalar(v) {
  if (v === null || v === undefined) return '<span class="muted">∅</span>';
  if (typeof v === 'string') return `"${escapeHtml(v)}"`;
  if (typeof v === 'number') {
    if (Number.isInteger(v)) return String(v);
    return v.toFixed(Math.min(6, (v.toString().split('.')[1] || '').length));
  }
  return escapeHtml(String(v));
}

function formatTripleValue(v) {
  if (typeof v === 'string') {
    if (v.length > 240) return JSON.stringify(v).slice(0, 240) + '…';
    return JSON.stringify(v);
  }
  const json = JSON.stringify(v);
  if (json.length <= 200) return json;
  return json.slice(0, 200) + '…';
}


// ─── presets / input handling ─────────────────────────────────────

function setupPresets() {
  document.querySelectorAll('.pg-preset').forEach(el => {
    el.addEventListener('click', () => {
      const key = el.dataset.preset;
      const data = PRESETS[key];
      if (!data) return;
      document.getElementById('pgInput').value = JSON.stringify(data);
      updateInputMeta();
    });
  });
}

function updateInputMeta() {
  const input = document.getElementById('pgInput').value;
  let count = 0;
  try {
    const parsed = parseInput(input);
    count = parsed.length;
  } catch { count = 0; }
  document.getElementById('pgInputCount').textContent =
    count === 0 ? '— values' : `${count.toLocaleString()} value${count === 1 ? '' : 's'}`;
  scheduleInspectorWarnings();  // re-validate: the inferred type may have changed
}


// ─── boilerplate (status, toast, dom helpers) ─────────────────────

function showSection(id) {
  const el = document.getElementById(id);
  if (el && el.classList.contains('hidden')) {
    el.classList.remove('hidden');
    el.classList.add('appearing');
    setTimeout(() => el.classList.remove('appearing'), 700);
  }
}

function updateStatus(label, detail) {
  const a = document.getElementById('statusLabel');
  const b = document.getElementById('statusDetail');
  if (a) a.textContent = label;
  if (b) b.textContent = detail;
}

function toast(msg, kind = 'info') {
  const t = document.createElement('div');
  t.className = `toast ${kind}`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => {
    t.classList.add('fading');
    setTimeout(() => t.remove(), 280);
  }, 2400);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}
function escapeAttr(s) { return escapeHtml(s); }


// ─── init ─────────────────────────────────────────────────────────

function init() {
  setupPresets();
  document.getElementById('pgInput').addEventListener('input', updateInputMeta);
  document.getElementById('pgRunBtn').addEventListener('click', runSteps);
  document.getElementById('pgClearPipeline').addEventListener('click', () => {
    state.pipeline = [];
    renderChips();
  });
  document.getElementById('pgLossyToggle').addEventListener('change', e => {
    state.lossy = e.target.checked;
  });

  // load default preset
  document.getElementById('pgInput').value = JSON.stringify(PRESETS.categorical);
  renderChips();
  updateInputMeta();
  updateStatus('IDLE', 'feature sequence loaded · adjust pipeline and run');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

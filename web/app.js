/* ════════════════════════════════════════════════════════════════
   COMPRESSION PLAYGROUND · app.js
   ─────────────────────────────────────────────────────────────────
   Thin UI shell — all encoding goes through the local server at
   /api/inspect and /api/encode, which call the real
   `encode_feature_df`. No encoder logic lives here.
   ════════════════════════════════════════════════════════════════ */

'use strict';

// Upload cap. Mirrored on the server in `server.py` (MAX_UPLOAD_BYTES).
const MAX_UPLOAD = 10 * 1024 * 1024;  // 10 MB

// ─────────────────────────  STATE  ─────────────────────────────────

const state = {
  file: null,
  filename: null,
  fileId: null,
  rowCount: 0,
  totalOriginalSize: 0,
  columns: [],          // [{ name, type, is_list, cardinality, avg_seq_len, non_null, total_elements, samples, original_size, recommended }]
  pipelines: {},        // { columnName: 'cat_rle_bp' | 'auto' }
  warnings: {},         // { columnName: [{ level, code, message, step_index }] } — from /api/validate
  encoded: null,        // last /api/encode response, normalised
  lossy: true,
};

// ─── UI metadata for the scheme picker (does not duplicate logic) ──

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


// ─────────────────────────  DEFAULT DATASET  ───────────────────────

async function loadDefaultDataset() {
  const btn = document.getElementById('loadSampleBtn');
  btn.disabled = true;
  updateStatus('READING', 'loading kuairand_demo.parquet · bundled sample dataset');
  try {
    // Fetch the raw parquet bytes so we can construct a real File object and
    // reuse the identical handleFile → /api/inspect → render path.
    const res = await fetch('/sample_datasets/kuairand_demo.parquet');
    if (!res.ok) throw new Error(`could not fetch sample: ${res.status}`);
    const buf = await res.arrayBuffer();
    const file = new File([buf], 'kuairand_demo.parquet', { type: 'application/octet-stream' });
    await handleFile(file);
  } catch (err) {
    console.error(err);
    updateStatus('ERROR', String(err.message || err).toLowerCase());
    toast(`could not load sample dataset: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
  }
}


// ─────────────────────────  FILE INTAKE  ───────────────────────────

function setupDropZone() {
  const dz = document.getElementById('dropZone');
  const fi = document.getElementById('fileInput');

  ['dragenter', 'dragover'].forEach(ev =>
    dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('hover'); }));
  ['dragleave', 'dragend', 'drop'].forEach(ev =>
    dz.addEventListener(ev, () => dz.classList.remove('hover')));

  dz.addEventListener('drop', e => {
    e.preventDefault();
    if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
  });

  fi.addEventListener('change', e => {
    if (e.target.files.length > 0) handleFile(e.target.files[0]);
  });
}

async function handleFile(file) {
  if (file.size > MAX_UPLOAD) {
    updateStatus('REJECTED', `file too large · ${formatBytes(file.size)} > 10 MB cap`);
    toast(`file too large: ${formatBytes(file.size)} (max 10 MB)`, 'error');
    return;
  }

  state.file = file;
  state.filename = file.name;
  updateStatus('READING', `parsing ${file.name} · ${formatBytes(file.size)} · recommender payload`);

  try {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/inspect', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `${res.status}`);

    state.fileId = data.id;
    state.rowCount = data.row_count;
    state.totalOriginalSize = data.total_size;
    state.columns = data.columns;
    state.pipelines = {}; // reset on new file
    state.warnings = {};  // reset on new file

    renderSchema();
    autoPickAll();          // apply heuristic recommendations from server
    renderPipelineComposer();
    showSection('section-schema');
    showSection('section-pipeline');

    updateStatus('READY',
      `${state.rowCount.toLocaleString()} rows · ${state.columns.length} features · ${formatBytes(state.totalOriginalSize)}`);
    toast(`loaded ${file.name}`);
  } catch (err) {
    console.error(err);
    updateStatus('ERROR', String(err.message || err).toLowerCase());
    toast(`could not read file: ${err.message}`, 'error');
  }
}


// ─────────────────────────  SCHEMA RENDER  ─────────────────────────

function renderSchema() {
  document.getElementById('filename').textContent = state.filename;
  document.getElementById('rowCount').textContent = state.rowCount.toLocaleString();
  document.getElementById('colCount').textContent = state.columns.length.toLocaleString();
  document.getElementById('origSize').textContent = formatBytes(state.totalOriginalSize);

  const tbody = document.getElementById('schemaBody');
  tbody.innerHTML = '';

  state.columns.forEach((col, i) => {
    const tr = document.createElement('tr');
    const typeLabel = col.is_list ? `list&lt;${col.type}&gt;` : col.type;
    tr.innerHTML = `
      <td class="col-num">${String(i + 1).padStart(2, '0')}</td>
      <td class="col-name">${escapeHtml(col.name)}</td>
      <td><span class="col-type-badge ${col.type}">${typeLabel}</span></td>
      <td class="col-card">${col.is_list ? (col.avg_seq_len || 0).toLocaleString() : '<span class="muted">—</span>'}</td>
      <td class="col-sample">${col.samples.length ? col.samples.map(s => escapeHtml(s)).join('<span class="sep">·</span>') : '<span class="muted">∅</span>'}</td>
      <td class="col-bytes">${formatBytes(col.original_size)}</td>
    `;
    tbody.appendChild(tr);
  });
}


// ─────────────────────────  PIPELINE COMPOSER  ─────────────────────

function renderPipelineComposer() {
  const list = document.getElementById('pipelineList');
  list.innerHTML = '';

  state.columns.forEach((col, idx) => {
    const row = document.createElement('div');
    row.className = 'col-row';
    row.dataset.col = col.name;

    const pipelineString = state.pipelines[col.name] || '';
    const rec = col.recommended;
    const lossy = pipelineString.split('_').some(s => SCHEME_INFO[s]?.lossy);

    row.innerHTML = `
      <div>
        <div class="col-row-name" title="${escapeAttr(col.name)}">${escapeHtml(col.name)}</div>
        <div class="col-row-meta" title="${escapeAttr((col.is_list ? `list<${col.type}>` : col.type) + ' · ' + formatBytes(col.original_size))}">
          ${col.is_list ? `list&lt;${col.type}&gt;` : col.type} · ${formatBytes(col.original_size)}
          ${lossy ? '<span class="lossy">⚠ lossy</span>' : ''}
        </div>
      </div>
      <div class="col-row-pipeline">
        ${renderPipelineChips(col.name, pipelineString)}
        ${renderAddSchemeButton(col.name, idx)}
      </div>
      <div class="col-row-rec" data-col="${escapeHtml(col.name)}" data-rec="${rec || ''}" title="${rec ? 'click to apply' : ''}">
        ${rec
          ? `<span class="arrow">↳</span><em>recommended</em><br><code>${rec}</code>`
          : `<em class="muted">no recommendation</em>`}
      </div>
      <div class="pipeline-warnings" data-col="${escapeAttr(col.name)}">${renderWarningsHtml(state.warnings[col.name])}</div>
    `;
    list.appendChild(row);
  });

  list.querySelectorAll('.col-row-rec').forEach(el => {
    el.addEventListener('click', () => {
      const r = el.dataset.rec;
      if (!r) return;
      state.pipelines[el.dataset.col] = r;
      renderPipelineComposer();
    });
  });

  list.querySelectorAll('.scheme-chip .x').forEach(el => {
    el.addEventListener('click', e => {
      e.stopPropagation();
      const col = el.dataset.col;
      const idx = parseInt(el.dataset.idx, 10);
      const cur = state.pipelines[col] || '';
      // 'auto' is a single chip; any × clears it.
      if (cur === 'auto') {
        state.pipelines[col] = '';
      } else {
        const steps = cur.split('_').filter(Boolean);
        steps.splice(idx, 1);
        state.pipelines[col] = steps.join('_');
      }
      renderPipelineComposer();
    });
  });

  list.querySelectorAll('.add-scheme-item').forEach(el => {
    el.addEventListener('click', e => {
      e.stopPropagation();
      const col = el.dataset.col;
      const code = el.dataset.code;
      const cur = state.pipelines[col] || '';
      // auto is mutually exclusive — replaces any existing pipeline.
      // Likewise picking a step from an 'auto' pipeline replaces it.
      if (code === 'auto' || cur === 'auto') {
        state.pipelines[col] = code;
      } else {
        state.pipelines[col] = cur ? `${cur}_${code}` : code;
      }
      renderPipelineComposer();
    });
  });

  list.querySelectorAll('details.add-scheme').forEach(d => {
    d.addEventListener('toggle', () => {
      if (d.open) {
        list.querySelectorAll('details.add-scheme').forEach(o => {
          if (o !== d) o.open = false;
        });
      }
    });
  });

  scheduleWarningRefresh();
}

// ─── improper-pipeline warnings (server-validated) ────────────────
// The composer never re-implements the encoder's validity rules — it asks
// /api/validate (which calls the same transition table the encoder uses) and
// paints whatever comes back. Refresh is debounced and stale responses are
// dropped so rapid chip edits don't race.

let _warnToken = 0;
let _warnTimer = null;

function scheduleWarningRefresh() {
  clearTimeout(_warnTimer);
  _warnTimer = setTimeout(refreshWarnings, 90);
}

async function refreshWarnings() {
  const token = ++_warnToken;
  const checks = [];
  state.columns.forEach(col => {
    const p = state.pipelines[col.name] || '';
    if (!p || p === 'auto') {
      state.warnings[col.name] = [];  // clear stale warnings for pass-through / auto
    } else {
      checks.push({ key: col.name, pipeline: p, type: col.type });
    }
  });

  if (checks.length === 0) {
    paintWarnings();
    return;
  }

  try {
    const res = await fetch('/api/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ checks }),
    });
    const data = await res.json();
    if (token !== _warnToken) return;  // a newer refresh superseded this one
    if (!res.ok) return;
    (data.results || []).forEach(r => { state.warnings[r.key] = r.warnings || []; });
    paintWarnings();
  } catch {
    /* validation is advisory — never block the composer on a failed fetch */
  }
}

function paintWarnings() {
  document.querySelectorAll('#pipelineList .pipeline-warnings[data-col]').forEach(box => {
    box.innerHTML = renderWarningsHtml(state.warnings[box.dataset.col]);
  });
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

function renderPipelineChips(colName, pipelineString) {
  if (!pipelineString) {
    return `<span class="pipeline-empty">⌁ pass through</span>`;
  }
  if (pipelineString === 'auto') {
    return `<span class="scheme-chip auto-chip" title="Auto-discover · DFS over all valid pipelines, picks smallest">
      <span class="label"><span class="auto-glyph">✦</span> auto</span>
      <span class="x" data-col="${escapeAttr(colName)}" data-idx="0" aria-label="remove">×</span>
    </span>`;
  }
  const steps = pipelineString.split('_').filter(Boolean);
  return steps.map((step, i) => {
    const arrow = i > 0
      ? `<span class="pipeline-arrow">▸</span>`
      : '';
    const info = SCHEME_INFO[step];
    const title = info ? `${info.name} — ${info.desc}` : step;
    return `${arrow}<span class="scheme-chip" title="${escapeAttr(title)}">
      <span class="label">${step}</span>
      <span class="x" data-col="${escapeAttr(colName)}" data-idx="${i}" aria-label="remove">×</span>
    </span>`;
  }).join('');
}

function renderAddSchemeButton(colName) {
  const pipelineString = state.pipelines[colName] || '';
  if (pipelineString === 'auto') return ''; // auto is mutually exclusive — no append

  const autoSection = `
    <div class="add-scheme-section">Auto-discover · DFS over candidate feature pipelines</div>
    <div class="add-scheme-item auto-item" data-col="${escapeAttr(colName)}" data-code="auto">
      <span class="code"><span class="auto-glyph">✦</span> auto</span>
      <span class="desc">search all valid pipelines (depth&nbsp;3) · pick smallest</span>
    </div>
  `;

  const sections = SCHEME_GROUPS.map(([title, codes]) => {
    const items = codes.map(code => {
      const info = SCHEME_INFO[code];
      const lossyTag = info.lossy ? '<span class="lossy-tag">lossy</span>' : '';
      return `<div class="add-scheme-item" data-col="${escapeAttr(colName)}" data-code="${code}">
        <span class="code">${code}${lossyTag}</span>
        <span class="desc">${info.desc}</span>
      </div>`;
    }).join('');
    return `
      <div class="add-scheme-section">${title}</div>
      ${items}
    `;
  }).join('');

  return `
    <details class="add-scheme">
      <summary>add</summary>
      <div class="add-scheme-menu">${autoSection}${sections}</div>
    </details>
  `;
}


// ─────────────────────────  ENCODE LOADING BAR  ────────────────────

function showEncodeLoader(rowCount, colCount) {
  const el = document.getElementById('encodeLoader');
  if (!el) return null;

  document.getElementById('encodeLoadStage').textContent = 'compressing…';
  document.getElementById('encodeLoadSub').textContent =
    `${rowCount.toLocaleString()} rows · ${colCount} feature columns`;
  document.getElementById('encodeLoadElapsed').textContent = '0.0s';

  el.classList.remove('hidden', 'leaving');
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  const startTime = performance.now();
  const elapsedEl = document.getElementById('encodeLoadElapsed');
  const timer = setInterval(() => {
    elapsedEl.textContent = ((performance.now() - startTime) / 1000).toFixed(1) + 's';
  }, 100);
  el._timer = timer;
  return el;
}

function hideEncodeLoader(el) {
  if (!el) return;
  clearInterval(el._timer);
  el.classList.add('leaving');
  setTimeout(() => el.classList.add('hidden'), 240);
}


// ─────────────────────────  ENCODE  ────────────────────────────────

async function runEncode() {
  if (!state.file) {
    toast('upload a file first', 'error');
    return;
  }
  updateStatus('ENCODING', 'encode_feature_df · compressing recommender payload');

  const schema = {};
  for (const [k, v] of Object.entries(state.pipelines)) if (v) schema[k] = v;
  const colCount = Object.keys(schema).length || state.columns.length;
  const loader = showEncodeLoader(state.rowCount, colCount);

  try {
    const fd = new FormData();
    fd.append('file', state.file);
    fd.append('schema', JSON.stringify(schema));
    fd.append('lossy', state.lossy ? 'true' : 'false');

    const start = performance.now();
    const res = await fetch('/api/encode', { method: 'POST', body: fd });
    const data = await res.json();
    const roundTrip = performance.now() - start;
    if (!res.ok) throw new Error(data.error || `${res.status}`);

    hideEncodeLoader(loader);
    state.encoded = data;
    renderOutput(roundTrip);
    showSection('section-output');

    const saved = data.total_orig - data.total_enc;
    const savedPct = data.total_orig === 0 ? 0 : (saved / data.total_orig) * 100;
    const savedMsg = savedPct >= 0
      ? `${savedPct.toFixed(1)}% space saved · server ${data.elapsed_ms.toFixed(0)}ms`
      : `${Math.abs(savedPct).toFixed(1)}% space added · server ${data.elapsed_ms.toFixed(0)}ms`;
    updateStatus('ENCODED', savedMsg);
    document.getElementById('section-output').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (err) {
    hideEncodeLoader(loader);
    console.error(err);
    updateStatus('ERROR', String(err.message || err).toLowerCase());
    toast(`encode failed: ${err.message}`, 'error');
  }
}

function autoPickAll() {
  state.columns.forEach(col => {
    if (col.recommended) state.pipelines[col.name] = col.recommended;
  });
  renderPipelineComposer();
}

function clearAll() {
  state.pipelines = {};
  renderPipelineComposer();
}


// ─────────────────────────  OUTPUT  ────────────────────────────────

function renderOutput(roundTripMs) {
  const { perColumn, total_orig, total_enc, elapsed_ms } = {
    perColumn: state.encoded.per_column,
    total_orig: state.encoded.total_orig,
    total_enc: state.encoded.total_enc,
    elapsed_ms: state.encoded.elapsed_ms,
  };
  const ratio = total_orig === 0 ? 1 : total_enc / total_orig;
  const saved = (1 - ratio) * 100;
  const savedBytes = total_orig - total_enc;

  setText('outRows',        state.encoded.row_count.toLocaleString());
  setText('outColCount',    perColumn.length.toLocaleString());
  setText('outOrig',        formatBytes(total_orig));
  setText('outOrigBytes',   `${total_orig.toLocaleString()} bytes`);
  setText('outEnc',         formatBytes(total_enc));
  setText('outEncBytes',    `${total_enc.toLocaleString()} bytes · server ${elapsed_ms.toFixed(0)}ms · rt ${roundTripMs.toFixed(0)}ms`);
  setText('outRatio',       ratio.toFixed(3) + '×');
  const savedEl = document.getElementById('outSaved');
  const savedLabelEl = savedEl.closest('.out-block')?.querySelector('.out-label');
  savedEl.className = savedEl.className.replace(/\bsaved-\w+/g, '').trim();
  if (saved >= 0) {
    savedEl.textContent = Math.abs(saved).toFixed(1) + '%';
    savedEl.classList.add('saved-pos');
    if (savedLabelEl) savedLabelEl.textContent = 'REDUCED';
  } else {
    savedEl.textContent = Math.abs(saved).toFixed(1) + '%';
    savedEl.classList.add('saved-neg');
    if (savedLabelEl) savedLabelEl.textContent = 'INCREASED';
  }
  setText('outSavedBytes',  `${savedBytes.toLocaleString()} bytes`);

  const sorted = [...perColumn].sort((a, b) => (b.orig_size - b.enc_size) - (a.orig_size - a.enc_size));
  const maxSize = Math.max(...sorted.map(c => c.orig_size), 1);

  const bars = document.getElementById('outputBars');
  bars.innerHTML = '';
  sorted.forEach((col, i) => {
    const r = col.enc_size / Math.max(1, col.orig_size);
    const savedPct = (1 - r) * 100;
    const cls = col.scheme ? (savedPct > 0.5 ? 'positive' : savedPct < -0.5 ? 'negative' : 'zero') : 'zero';
    const isAutoPicked = col.requested === 'auto' && !!col.scheme;

    const bar = document.createElement('div');
    bar.className = 'bar-row';
    bar.innerHTML = `
      <div class="bar-name">${escapeHtml(col.name)}</div>
      <div class="bar-track" title="${formatBytes(col.orig_size)} → ${formatBytes(col.enc_size)}">
        <div class="bar-orig" style="width: ${(col.orig_size / maxSize) * 100}%"></div>
        <div class="bar-enc" style="width: 0%"></div>
      </div>
      <div class="bar-savings ${cls}">${col.scheme ? Math.abs(savedPct).toFixed(1) + '% ' + (savedPct >= 0 ? 'saved' : 'added') : '—'}</div>
    `;
    bars.appendChild(bar);

    requestAnimationFrame(() => {
      setTimeout(() => {
        const enc = bar.querySelector('.bar-enc');
        if (enc) enc.style.width = ((col.enc_size / maxSize) * 100) + '%';
      }, 30 + i * 40);
    });
  });

  // wire format preview
  const wirePayload = {};
  perColumn.forEach(c => { wirePayload[c.name + '_enc'] = c.wire_value || JSON.stringify([null]); });
  document.getElementById('wireOutput').innerHTML = formatWireFormat(wirePayload);

  // dynamic row count in the wire-format header
  const noteEl = document.querySelector('.wire-note');
  if (noteEl) {
    noteEl.innerHTML = `representative · row <span class="hot">1</span> of ${state.encoded.row_count.toLocaleString()}`;
  }

  // populate §05 — scheme distribution
  renderDistribution();
  showSection('section-distribution');
}


// ─────────────────────────  §05 SCHEME DISTRIBUTION  ───────────────

const _distState = { selected: '__all__', filter: '' };

function renderDistribution() {
  if (!state.encoded) return;
  // Reset selection on each new encode so a column from a previous file
  // doesn't linger and produce "column not found".
  if (_distState.selected !== '__all__' &&
      !state.encoded.per_column.find(c => c.name === _distState.selected)) {
    _distState.selected = '__all__';
  }
  // Wire event delegation ONCE per session. The list itself is re-rendered
  // on every selection/filter change, so handlers on individual items would
  // die after the first click — delegation on the stable parent survives.
  if (!_distState.wired) {
    wireDistEvents();
    _distState.wired = true;
  }
  renderDistColumnList();
  renderDistHistogram();
}

function renderDistColumnList() {
  const list = document.getElementById('distColList');
  if (!list) return;
  const filter = _distState.filter.toLowerCase();
  const cols = state.encoded.per_column;
  const totalRows = state.encoded.row_count;

  const allRow = `
    <button class="dist-col-item dist-col-all ${_distState.selected === '__all__' ? 'selected' : ''}"
            data-col="__all__">
      <span class="dist-col-glyph">✦</span>
      <span class="dist-col-name">All features</span>
      <span class="dist-col-count">${(cols.length * totalRows).toLocaleString()}</span>
    </button>
  `;

  const matched = cols
    .filter(c => !filter || c.name.toLowerCase().includes(filter))
    .map(c => {
      const distinct = (c.scheme_breakdown || []).filter(b => b.scheme).length;
      const sel = _distState.selected === c.name ? 'selected' : '';
      const skipped = c.skipped_rows ? ` <span class="dist-col-skip" title="rows kept unencoded">${c.skipped_rows}</span>` : '';
      return `
        <button class="dist-col-item ${sel}" data-col="${escapeAttr(c.name)}">
          <span class="dist-col-name">${escapeHtml(c.name)}</span>
          <span class="dist-col-distinct">${distinct}</span>${skipped}
        </button>
      `;
    });

  list.innerHTML = allRow + (matched.length === 0
    ? `<div class="dist-col-empty">no columns match</div>`
    : matched.join(''));
}

function aggregatedBreakdown() {
  const totals = new Map();
  for (const col of state.encoded.per_column) {
    for (const b of col.scheme_breakdown || []) {
      const key = b.scheme === null ? '__none__' : b.scheme;
      totals.set(key, (totals.get(key) || 0) + b.count);
    }
  }
  return [...totals.entries()]
    .map(([s, n]) => ({ scheme: s === '__none__' ? null : s, count: n }))
    .sort((a, b) => b.count - a.count);
}

function renderDistHistogram() {
  const sel = _distState.selected;
  const eyebrow = document.getElementById('distEyebrow');
  const title = document.getElementById('distTitle');
  const meta = document.getElementById('distMeta');
  const bars = document.getElementById('distBars');
  if (!eyebrow || !title || !meta || !bars) return; // §05 not in DOM (stale HTML?)

  let breakdown, titleText, eyebrowText, metaText;

  if (sel === '__all__') {
    breakdown = aggregatedBreakdown();
    eyebrowText = 'AGGREGATE';
    titleText = 'All features · all rows';
    const rowsTotal = state.encoded.per_column.length * state.encoded.row_count;
    metaText = `${state.encoded.per_column.length.toLocaleString()} features × ${state.encoded.row_count.toLocaleString()} rows = ${rowsTotal.toLocaleString()} encoded payloads`;
  } else {
    const col = state.encoded.per_column.find(c => c.name === sel);
    if (!col) {
      bars.innerHTML = '<div class="dist-col-empty">column not found</div>';
      return;
    }
    breakdown = (col.scheme_breakdown || []).slice().sort((a, b) => b.count - a.count);
    eyebrowText = col.is_list ? `LIST<${col.type || '—'}>` : (col.type || '—').toUpperCase();
    titleText = col.name;
    const ratio = col.enc_size / Math.max(1, col.orig_size);
    const saved = (1 - ratio) * 100;
    metaText = `${col.row_count.toLocaleString()} rows · ${formatBytes(col.orig_size)} → ${formatBytes(col.enc_size)} (${Math.abs(saved).toFixed(1)}% ${saved >= 0 ? 'saved' : 'added'})`;
  }

  eyebrow.textContent = eyebrowText;
  title.textContent = titleText;
  meta.textContent = metaText;

  if (!breakdown || breakdown.length === 0) {
    bars.innerHTML = '<div class="dist-col-empty">no rows encoded</div>';
    return;
  }

  const total = breakdown.reduce((s, b) => s + b.count, 0);
  const max = Math.max(...breakdown.map(b => b.count), 1);

  bars.innerHTML = breakdown.map(b => {
    const widthPct = (b.count / max) * 100;
    const sharePct = total === 0 ? 0 : (b.count / total) * 100;
    const isNone = !b.scheme;
    const label = isNone ? 'none · skipped' : b.scheme;
    return `
      <div class="dist-bar-row ${isNone ? 'is-none' : ''}">
        <div class="dist-bar-label" title="${escapeAttr(label)}">${escapeHtml(label)}</div>
        <div class="dist-bar-track">
          <div class="dist-bar-fill" style="width: 0%" data-target="${widthPct.toFixed(2)}"></div>
        </div>
        <div class="dist-bar-count">${b.count.toLocaleString()}</div>
        <div class="dist-bar-pct">${sharePct.toFixed(1)}%</div>
      </div>
    `;
  }).join('');

  // animate fills
  requestAnimationFrame(() => {
    bars.querySelectorAll('.dist-bar-fill').forEach((el, i) => {
      setTimeout(() => { el.style.width = el.dataset.target + '%'; }, 30 + i * 30);
    });
  });

  // when a single column is selected, append the wire-format triple panel so
  // the relationship between scheme, aux, and bytes is explicit. For "All
  // columns", append a hint pointing at the per-column drilldown plus the
  // triple of the first encoded column so the wire-format shape is always
  // visible at least once.
  if (sel !== '__all__') {
    const col = state.encoded.per_column.find(c => c.name === sel);
    if (col) {
      bars.insertAdjacentHTML('beforeend', renderWireTriplePanel(col));
    }
  } else {
    const example = state.encoded.per_column.find(c => c.wire_aux && Object.keys(c.wire_aux).length > 0)
                 || state.encoded.per_column.find(c => c.wire_value);
    if (example) {
      bars.insertAdjacentHTML('beforeend', `
        <div class="dist-hint">
          <span class="hot-italic">↓</span>&nbsp;Click any feature on the left to inspect its full
          <code>[value, scheme, aux]</code> encoded entry. Showing
          <code>${escapeHtml(example.name)}</code> as a sample below.
        </div>
      `);
      bars.insertAdjacentHTML('beforeend', renderWireTriplePanel(example));
    }
  }
}

function renderWireTriplePanel(col) {
  const value = col.wire_value;
  let parsed = null;
  try { parsed = value ? JSON.parse(value) : null; } catch {}
  const valueOnly = parsed && parsed.length >= 1 ? parsed[0] : null;
  const scheme = col.wire_scheme || col.scheme;
  const aux = col.wire_aux || {};
  const auxEntries = Object.entries(aux);

  const valuePreview = valueOnly === null ? '<em class="muted">—</em>'
    : `<pre class="wire-triple-pre">${escapeHtml(formatTripleValue(valueOnly))}</pre>`;

  const auxPretty = auxEntries.length === 0
    ? '<em class="muted">{ }  ·  no aux for this scheme</em>'
    : `<pre class="wire-triple-pre">${escapeHtml(JSON.stringify(aux, null, 2))}</pre>`;

  const totalLen = value ? value.length : 0;

  // Payload comparison — uncompressed vs compressed for this row
  const uncompressedCell = col.wire_orig_cell;
  const uncompressedBytes = col.wire_orig_bytes || 0;
  const savedBytes = uncompressedBytes - totalLen;
  const savedPct = uncompressedBytes > 0 ? (savedBytes / uncompressedBytes) * 100 : 0;
  const savedClass = savedBytes > 0 ? 'shrunk' : (savedBytes < 0 ? 'grew' : '');
  const savedLabel = savedBytes === 0
    ? '±0 B'
    : `${savedBytes > 0 ? '−' : '+'}${Math.abs(savedBytes)} B · ${(savedPct >= 0 ? '−' : '+') + Math.abs(savedPct).toFixed(1)}%`;

  const uncompressedPreview = uncompressedCell == null
    ? '<em class="muted">—</em>'
    : `<pre class="wire-triple-pre">${escapeHtml(formatTripleValue(uncompressedCell))}</pre>`;

  const compressedTriple = auxEntries.length > 0 ? [valueOnly, scheme, aux] : [valueOnly, scheme];
  const compressedPreview = valueOnly === null
    ? '<em class="muted">—</em>'
    : `<pre class="wire-triple-pre">${escapeHtml(formatTripleValue(compressedTriple))}</pre>`;

  const payloadCompare = (uncompressedBytes > 0 && totalLen > 0) ? `
    <div class="pg-payload-compare">
      <div class="pg-payload-compare-head">
        <span class="pg-payload-compare-title">PAYLOAD COMPARISON</span>
        <span class="pg-payload-compare-meta muted">row 1 · as stored by <code>encode_feature_payload</code></span>
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
            <span class="pg-payload-cell-bytes hot">${totalLen} B</span>
          </div>
          <div class="pg-payload-cell-note muted">json.dumps([value, scheme, aux])</div>
          ${compressedPreview}
        </div>
        <div class="pg-payload-compare-savings ${savedClass}">
          <div class="pg-payload-savings-num">${savedLabel}</div>
          <div class="pg-payload-savings-sub muted">bytes saved</div>
        </div>
      </div>
    </div>
  ` : '';

  return `
    <div class="wire-triple">
      <div class="wire-triple-head">
        <div class="wire-triple-eyebrow">SAMPLE ENCODED ENTRY · ROW 1 of ${(col.row_count || 0).toLocaleString()}</div>
        <div class="wire-triple-title"><code>${escapeHtml(col.name)}_enc</code> = <span class="hot-italic">[value, scheme, aux]</span></div>
        <div class="wire-triple-meta">${totalLen.toLocaleString()} bytes total</div>
      </div>
      <div class="wire-triple-grid">
        <div class="wire-triple-cell">
          <div class="wire-triple-label">[0] value</div>
          ${valuePreview}
        </div>
        <div class="wire-triple-cell">
          <div class="wire-triple-label">[1] scheme</div>
          <pre class="wire-triple-pre wire-triple-scheme">${scheme ? escapeHtml(JSON.stringify(scheme)) : '<em class="muted">— (skipped)</em>'}</pre>
        </div>
        <div class="wire-triple-cell">
          <div class="wire-triple-label">[2] aux</div>
          ${auxPretty}
        </div>
      </div>
      ${payloadCompare}
    </div>
  `;
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

function wireDistEvents() {
  // Delegate clicks: list innerHTML is rebuilt on every selection change,
  // so we must listen on the stable parent rather than per-item.
  const list = document.getElementById('distColList');
  if (list) {
    list.addEventListener('click', e => {
      const item = e.target.closest('.dist-col-item');
      if (!item || !list.contains(item)) return;
      const col = item.dataset.col;
      if (!col || col === _distState.selected) return;
      _distState.selected = col;
      renderDistColumnList();
      renderDistHistogram();
    });
  }

  const search = document.getElementById('distSearch');
  if (search) {
    search.addEventListener('input', e => {
      _distState.filter = e.target.value;
      renderDistColumnList();
    });
  }
}

function renderSchemeBreakdown(col, isAutoPicked) {
  // No longer used in the bar list — the dedicated §05 distribution view owns
  // per-row counts. Kept as a helper for tooltips elsewhere.
  return col.scheme || '—';
}

function renderAuxKeys(col) {
  // Compact reminder that the wire entry is `[value, scheme, aux]` — keys of
  // the representative row's aux dict, no values (those can be enormous, e.g.
  // a 5,000-entry stoi).
  const keys = col.wire_aux_keys || [];
  if (keys.length === 0) return '';
  const chips = keys.slice(0, 4).map(k => `<span class="aux-key">${escapeHtml(k)}</span>`).join('');
  const more = keys.length > 4 ? `<span class="aux-more">+${keys.length - 4}</span>` : '';
  return ` <span class="aux-keys" title="auxiliary info dict from row 1 — part of the encoded entry [value, scheme, aux]">aux: ${chips}${more}</span>`;
}

function formatWireFormat(payload) {
  const lines = [`<span class="punct">{</span>`];
  const entries = Object.entries(payload);
  entries.forEach(([k, v], i) => {
    let inner = String(v);
    if (inner.length > 360) {
      inner = inner.slice(0, 320) + ` … <span class="punct">// ${(v.length - 320).toLocaleString()} chars truncated</span> … ` + inner.slice(-30);
    }
    let coloured = escapeHtml(inner);
    coloured = coloured.replace(/(&quot;[a-z0-9_]+&quot;)(?=,)/g, m => `<span class="scheme">${m}</span>`);
    lines.push(`  <span class="key">"${escapeHtml(k)}"</span><span class="punct">:</span> <span class="val">${coloured}</span>${i < entries.length - 1 ? '<span class="punct">,</span>' : ''}`);
  });
  lines.push(`<span class="punct">}</span>`);
  return lines.join('\n');
}


// ─────────────────────────  UI WIRING  ─────────────────────────────

function setupButtons() {
  document.getElementById('encodeBtn').addEventListener('click', runEncode);
  document.getElementById('loadSampleBtn').addEventListener('click', e => {
    e.preventDefault();   // don't let the label's for= open the file picker
    e.stopPropagation();
    loadDefaultDataset();
  });
  document.getElementById('autoAllBtn').addEventListener('click', () => {
    state.columns.forEach(col => { state.pipelines[col.name] = 'auto'; });
    renderPipelineComposer();
    toast('auto-discover applied · press encode to search');
  });
  document.getElementById('clearBtn').addEventListener('click', () => {
    clearAll();
    toast('pipelines cleared');
  });
  document.getElementById('lossyToggle').addEventListener('change', e => {
    state.lossy = e.target.checked;
  });
  document.getElementById('copyWire').addEventListener('click', copyWire);
}

async function copyWire() {
  const txt = document.getElementById('wireOutput').textContent;
  try {
    await navigator.clipboard.writeText(txt);
    const btn = document.getElementById('copyWire');
    btn.classList.add('copied');
    btn.textContent = 'copied ✓';
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.textContent = 'copy';
    }, 1400);
  } catch (e) {
    toast('clipboard unavailable', 'error');
  }
}

function showSection(id) {
  const el = document.getElementById(id);
  if (el.classList.contains('hidden')) {
    el.classList.remove('hidden');
    el.classList.add('appearing');
    setTimeout(() => el.classList.remove('appearing'), 700);
  }
}

function updateStatus(label, detail) {
  document.getElementById('statusLabel').textContent = label;
  document.getElementById('statusDetail').textContent = detail;
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


// ─────────────────────────  FORMATTERS  ────────────────────────────

function formatBytes(b) {
  if (b == null || isNaN(b)) return '—';
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(2)} KB`;
  if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(2)} MB`;
  return `${(b / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}

function escapeAttr(s) { return escapeHtml(s); }

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}


// ─────────────────────────  INIT  ──────────────────────────────────

function init() {
  setupDropZone();
  setupButtons();
  updateStatus('IDLE', 'awaiting feature payload');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

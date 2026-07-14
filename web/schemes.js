/* ═════════════════════════════════════════════════════════════════
   SCHEMES · animated reference page
   Each scheme defines a list of frames; a shared player renders them
   with play / pause / step / reset.  All data is hardcoded.
   ═════════════════════════════════════════════════════════════════ */

// ─── tiny dom helpers ──────────────────────────────────────────────
const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};
const esc = (s) => String(s).replace(/[&<>"']/g, c => ({
  '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
}[c]));

// ─── frame primitives ──────────────────────────────────────────────
// each frame is { commentary, rows: [...], aux: [...], bits, bytes, meter }
//
// row: { label, cells: [{ value, cls?, sub? }] }
// aux: array of "key=value" strings
// bits: array of 0/1 (or 'H' header marker) groups – or null
// bytes: array of { hex, label, cls } – or null
// meter: { orig, encoded, savedPct } – or null

function rowHTML(row) {
  const cells = row.cells.map(c => {
    const cls   = ['sch-cell', c.cls || ''].filter(Boolean).join(' ');
    const sub   = c.sub ? `<sub>${esc(c.sub)}</sub>` : '';
    const orig  = c.orig != null ? ` data-orig="${esc(c.orig)}"` : '';
    return `<div class="${cls}"${orig}>${esc(c.value)}${sub}</div>`;
  }).join('');
  return `<div class="sch-row">
    <div class="sch-row-label">${esc(row.label)}</div>
    <div class="sch-cells">${cells}</div>
  </div>`;
}

function bitsHTML(bits) {
  if (!bits || !bits.length) return '';
  const inner = bits.map(b => {
    if (b === '|') return `<div class="sch-bit sep"></div>`;
    if (b === 'H1') return `<div class="sch-bit header">1</div>`;
    if (b === 'H0') return `<div class="sch-bit header">0</div>`;
    if (b === 1)    return `<div class="sch-bit one">1</div>`;
    if (b === 0)    return `<div class="sch-bit zero">0</div>`;
    return `<div class="sch-bit">${esc(b)}</div>`;
  }).join('');
  return `<div class="sch-bits">${inner}</div>`;
}

function bytesHTML(bytes) {
  if (!bytes || !bytes.length) return '';
  const inner = bytes.map(b => {
    const cls = ['sch-byte', b.cls || ''].filter(Boolean).join(' ');
    const lbl = b.label ? ` <span style="opacity:.55">${esc(b.label)}</span>` : '';
    return `<div class="${cls}">${esc(b.hex)}${lbl}</div>`;
  }).join('');
  return `<div class="sch-bytes">${inner}</div>`;
}

function auxHTML(aux) {
  if (!aux || !aux.length) return `<div class="sch-aux"></div>`;
  const chips = aux.map(([k, v]) =>
    `<span class="kv"><b>${esc(k)}</b>=${esc(v)}</span>`
  ).join('');
  const defs = aux.filter(a => a[2]).map(([k, , desc]) =>
    `<div class="sch-aux-def"><b>${esc(k)}</b> <span>${desc}</span></div>`
  ).join('');
  return `<div class="sch-aux-block">
    <div class="sch-aux">${chips}</div>
    ${defs ? `<div class="sch-aux-defs">${defs}</div>` : ''}
  </div>`;
}

function meterHTML(meter) {
  if (!meter) return '';
  const saved = meter.savedPct != null
    ? ` &middot; <span class="saved">saved ${meter.savedPct}</span>` : '';
  return `<div class="sch-meter">
    <span>orig <b>${esc(meter.orig)}</b></span>
    <span>encoded <b>${esc(meter.encoded)}</b></span>
    ${saved}
  </div>`;
}

function renderFrame(frame) {
  const parts = [];
  parts.push(`<div class="sch-commentary">${frame.commentary || ''}</div>`);
  const canvas = [];
  (frame.rows || []).forEach((row, i) => {
    if (i > 0) canvas.push(`<div class="sch-arrow">↓</div>`);
    canvas.push(rowHTML(row));
  });
  if (frame.bits)  { canvas.push(`<div class="sch-arrow">↓</div>`); canvas.push(bitsHTML(frame.bits)); }
  if (frame.bytes) { canvas.push(`<div class="sch-arrow">↓</div>`); canvas.push(bytesHTML(frame.bytes)); }
  parts.push(`<div class="sch-canvas">${canvas.join('')}</div>`);
  parts.push(auxHTML(frame.aux));
  parts.push(meterHTML(frame.meter));
  return parts.join('');
}

// ─── scheme definitions ────────────────────────────────────────────
// helper: build a row of plain cells
const mkRow = (label, values, perCellCls = null) => ({
  label,
  cells: values.map((v, i) => ({
    value: v,
    cls: typeof perCellCls === 'function' ? perCellCls(v, i) : perCellCls
  }))
});

const SCHEMES = [];

// ─── 1. CAT — categorical ──────────────────────────────────────────
(function () {
  const input = ['WEB', 'WEB', 'MOBILE', 'WEB', 'TABLET', 'MOBILE'];
  const stoi  = { WEB: 0, MOBILE: 1, TABLET: 2 };
  const encoded = input.map(v => stoi[v]);

  const frames = [
    {
      commentary: 'Input is a list of repeating string labels — six values, three distinct.',
      rows: [mkRow('input', input)]
    },
    {
      commentary: 'Count frequencies. <em>WEB</em> appears three times, <em>MOBILE</em> twice, <em>TABLET</em> once.',
      rows: [
        mkRow('input', input, v => v === 'WEB' ? 'hl' : ''),
        mkRow('frequency tally', ['WEB ×3', 'MOBILE ×2', 'TABLET ×1'], 'dom')
      ]
    },
    {
      commentary: 'Assign ids by frequency — the most common label gets the shortest code (id 0).',
      rows: [mkRow('input', input)],
      aux: [
        ['stoi.WEB',    '0', 'string &rarr; int. Most-frequent label gets id 0 so downstream <code>bp</code> can pack it in the fewest bits.'],
        ['stoi.MOBILE', '1', 'next most common.'],
        ['stoi.TABLET', '2', 'least common.']
      ]
    },
    {
      commentary: 'Substitute each label with its id. Strings become ints — ready for a downstream packer.',
      rows: [
        mkRow('input', input, 'dim'),
        mkRow('encoded', encoded.map(String), 'added')
      ],
      aux: [['stoi', '{WEB:0, MOBILE:1, TABLET:2}', 'the dictionary the decoder needs to invert the mapping. Stored once per feature, regardless of sequence length.']],
      meter: { orig: '52 B', encoded: '13 B', savedPct: '75 %' }
    }
  ];

  SCHEMES.push({
    code: 'cat',
    name: 'Categorical',
    tagline: 'strings → ints (dictionary encoding)',
    blurb: 'Maps each unique string to an integer id. The most-frequent label receives id 0, so downstream <code>bp</code> can pack the bulk of the sequence using fewer bits.',
    frames
  });
})();

// ─── 2. QUANT — scalar quantization ────────────────────────────────
(function () {
  const input  = [0.13, 0.42, 0.78, 0.95, 0.04, 0.61];
  const bits   = 3;          // for visual compactness
  const lo = Math.min(...input);
  const hi = Math.max(...input);
  const levels = (1 << bits) - 1;
  const scale  = (hi - lo) / levels;
  const q      = input.map(x => Math.round((x - lo) / scale));

  const frames = [
    {
      commentary: 'Input is a list of floats in roughly [0, 1]. We want to compress them down to ' + bits + '-bit integers.',
      rows: [mkRow('input (float)', input.map(v => v.toFixed(2)))]
    },
    {
      commentary: `Find the range. <em>min</em>=${lo}, <em>max</em>=${hi}. With ${bits} bits we have ${levels + 1} levels.`,
      rows: [mkRow('input (float)', input.map((v, i) =>
        v === lo || v === hi ? v.toFixed(2) : v.toFixed(2)
      ), (v, i) => (input[i] === lo || input[i] === hi) ? 'hl' : '')],
      aux: [
        ['min',   lo,                'smallest input value &mdash; sets the lower edge of the quantization grid.'],
        ['max',   hi,                'largest input value &mdash; sets the upper edge.'],
        ['scale', scale.toFixed(4),  'step size between adjacent integer levels: <code>(max &minus; min) / (2&#8319; &minus; 1)</code>.'],
        ['q_bits', bits,             'number of bits used per quantized integer; here ' + bits + ' &rarr; ' + (levels + 1) + ' levels.']
      ]
    },
    {
      commentary: `Quantize: <code>q = round((x − min) / scale)</code>. Each float collapses to an integer in [0, ${levels}].`,
      rows: [
        mkRow('input (float)', input.map(v => v.toFixed(2)), 'dim'),
        mkRow('q (int)', q.map(String), 'added')
      ],
      aux: [
        ['q_scale', scale.toFixed(4), 'multiplier the decoder applies: <code>x &asymp; q &middot; q_scale + offset</code>. A value of 0 signals a constant input.'],
        ['q_zp',    '0',              'zero point &mdash; the integer that maps back to 0.0 (asymmetric) or the offset added before scaling (symmetric).'],
        ['q_bits',  bits,             'bits per quantized integer; defines the integer range [0, 2&#8319; &minus; 1].'],
        ['q_sym',   '0',              '1 if symmetric mode (data centered near 0), 0 if asymmetric. Here the range is &asymp; [0, 1], so asymmetric.']
      ],
      meter: { orig: '48 B', encoded: '6 B + aux', savedPct: '≈ 78 %' }
    }
  ];

  SCHEMES.push({
    code: 'quant',
    name: 'Quantization',
    tagline: 'floats → small ints (lossy)',
    blurb: 'Maps floats into the integer range [0, 2ⁿ−1] using an affine scale. Lossy — but the loss is bounded and recoverable to within ½&middot;scale. Pairs naturally with <code>bp</code>.',
    frames
  });
})();

// ─── 3. DEL — delta ───────────────────────────────────────────────
(function () {
  const input = [100, 102, 105, 104, 108, 110];
  const v0    = input[0];
  const deltas = input.slice(1).map((v, i) => v - input[i]);

  const frames = [
    {
      commentary: 'Input is a smooth, near-monotonic sequence. Successive values differ by only 1–4 — wasteful to store in full.',
      rows: [mkRow('input', input.map(String))]
    },
    {
      commentary: 'Save the first value <em>v₀</em> separately. Everything else will be expressed relative to its predecessor.',
      rows: [mkRow('input', input.map(String), (v, i) => i === 0 ? 'hl' : '')],
      aux: [['v0', String(v0), 'the first value of the original sequence. The decoder needs it to reconstruct the absolute series &mdash; everything else is just differences from here.']]
    },
    {
      commentary: 'Replace each value with its <em>delta</em> from the previous. The range collapses from [100..110] down to [−1..4].',
      rows: [
        mkRow('input', input.map(String), 'dim'),
        mkRow('deltas (Δ)', deltas.map(d => (d >= 0 ? '+' : '') + d), 'added')
      ],
      aux: [['v0', String(v0), 'starting value. Decoding is a running sum: <code>x&#8336; = v0 + &Sigma; &Delta;</code>.']],
      meter: { orig: '18 B', encoded: '8 B + v0', savedPct: '≈ 50 %' }
    }
  ];

  SCHEMES.push({
    code: 'del',
    name: 'Delta',
    tagline: 'value → difference from predecessor',
    blurb: 'A reducer that exploits smoothness: monotonic / slowly-changing sequences have small deltas, which downstream packers can store in a fraction of the original bit width.',
    frames
  });
})();

// ─── 4. RLE — run length ───────────────────────────────────────────
(function () {
  const input = ['A','A','A','B','B','C','C','C','C'];
  // computed runs
  const runs = [['A',3],['B',2],['C',4]];

  // helper to highlight a single run window
  const winCls = (start, len) => (v, i) =>
    i >= start && i < start + len ? 'hl run-pair' : '';

  const flat = runs.reduce((a, [v, c]) => a.concat([v, String(c)]), []);

  const frames = [
    {
      commentary: 'Input has long runs of equal values — three A’s, two B’s, four C’s.',
      rows: [mkRow('input', input)]
    },
    {
      commentary: 'Scan from the left. The first run is <em>A × 3</em> — emit <code>[A, 3]</code>.',
      rows: [
        mkRow('input', input, winCls(0, 3)),
        mkRow('emitted', ['A', '3'], 'added')
      ]
    },
    {
      commentary: 'Next run: <em>B × 2</em>. Append <code>[B, 2]</code>.',
      rows: [
        mkRow('input', input, winCls(3, 2)),
        mkRow('emitted', ['A','3','B','2'], (v, i) => i < 2 ? '' : 'added')
      ]
    },
    {
      commentary: 'Final run: <em>C × 4</em>. The output is a flat <em>[value, count, value, count, …]</em> sequence.',
      rows: [
        mkRow('input', input.map(String), 'dim'),
        mkRow('encoded', flat, 'added')
      ],
      meter: { orig: '27 B', encoded: '13 B', savedPct: '≈ 52 %' }
    }
  ];

  SCHEMES.push({
    code: 'rle',
    name: 'Run-Length',
    tagline: 'collapse runs of equal values',
    blurb: 'Replaces runs of equal values with <code>[value, count]</code> pairs. Hugely effective on sequences with long plateaus — categorical channels, sorted data, sparse flags.',
    frames
  });
})();

// ─── 5. STL — sentinel ─────────────────────────────────────────────
(function () {
  const input = [1842, 1845, 0, 1847, 1850, 0, 1853];
  const positions = [];
  input.forEach((v, i) => { if (v === 0) positions.push(i); });
  const clean = input.filter(v => v !== 0);

  const frames = [
    {
      commentary: 'Input is a tight range [1842..1853] — except for stray <em>0</em> values that blow up the apparent bit-width.',
      rows: [mkRow('input', input.map(String))]
    },
    {
      commentary: 'Compute the median and inter-quartile range. Values beyond <em>median ± k · IQR</em> are flagged as sentinels.',
      rows: [mkRow('input', input.map(String), (v, i) => v == 0 ? 'sentinel' : '')],
      aux: [
        ['median', '1847', 'middle of the sorted data &mdash; the robust centre used for outlier detection.'],
        ['IQR',    '6',    'inter-quartile range (Q3 &minus; Q1) &mdash; the robust spread.'],
        ['k',      '3.0',  'sensitivity. Any value outside <code>median &plusmn; k &middot; IQR</code> is flagged as a sentinel.']
      ]
    },
    {
      commentary: 'Strip the sentinels from the sequence; record their positions in <em>snt_ranges</em>.',
      rows: [
        mkRow('input',  input.map(String), (v, i) => v == 0 ? 'struck' : ''),
        mkRow('clean',  clean.map(String), 'added')
      ],
      aux: [
        ['snt_ranges', `{0: [[${positions[0]}], [${positions[1]}]]}`,
          'a <code>{sentinel_value: [[start, end], &hellip;]}</code> map remembering where each outlier was. Single-position ranges collapse to <code>[pos]</code>.'],
        ['length', String(input.length),
          'the original sequence length. Needed because the clean list is shorter &mdash; the decoder must know how many slots to reconstruct.']
      ],
      meter: { orig: 'range = 1853', encoded: 'range = 11', savedPct: 'bits/value: 11 → 4' }
    }
  ];

  SCHEMES.push({
    code: 'stl',
    name: 'Sentinel',
    tagline: 'strip outliers, store positions',
    blurb: 'Detects outlier values via the IQR method, removes them from the sequence, and remembers <em>where</em> they were. The remaining clean range packs far tighter downstream.',
    frames
  });
})();

// ─── 6. BM — bitmap ────────────────────────────────────────────────
(function () {
  const input = [1,0,1,1,0,0,1,0,1,1];
  const count = input.length;
  // header: byte0 = count & 0xFF, byte1 = (count>>8) (no constant flag)
  const b0 = count & 0xff;
  const b1 = (count >> 8) & 0xff;
  // payload bytes (MSB first)
  const padded = input.slice();
  while (padded.length % 8) padded.push(0);
  const payloadBytes = [];
  for (let i = 0; i < padded.length; i += 8) {
    let byte = 0;
    for (let j = 0; j < 8; j++) byte = (byte << 1) | padded[i + j];
    payloadBytes.push(byte);
  }

  const hex = (n, w = 2) => n.toString(16).toUpperCase().padStart(w, '0');

  const frames = [
    {
      commentary: 'A binary sequence of ' + count + ' values — purely <em>0</em>s and <em>1</em>s.',
      rows: [mkRow('input', input.map(String), v => v === 1 ? 'hl' : 'dim')]
    },
    {
      commentary: 'Build a 2-byte header: low 8 bits of <em>count</em>, then high 6 bits + a constant flag (0 here).',
      rows: [mkRow('input', input.map(String), v => v === 1 ? 'hl' : 'dim')],
      bytes: [
        { hex: '0x' + hex(b0), label: 'count.lo', cls: 'header' },
        { hex: '0x' + hex(b1), label: 'count.hi|flags', cls: 'header' }
      ],
      aux: [
        ['count',          String(count), 'number of bits in the sequence. Stored as a 14-bit integer (low 8 bits in byte 0, high 6 bits in byte 1) &mdash; max length 16 383.'],
        ['constant_flag',  '0',           '1 if every bit is the same value (in which case no payload follows); 0 otherwise.'],
        ['constant_value', '&mdash;',     'when <code>constant_flag</code>=1, the bit (0 or 1) that fills the entire sequence. Unused here.']
      ]
    },
    {
      commentary: 'Pack the bits MSB-first into bytes. Ten bits become <em>⌈10/8⌉ = 2</em> bytes of payload.',
      rows: [mkRow('input', input.map(String), v => v === 1 ? 'hl' : 'dim')],
      bits: [
        ...input.slice(0, 8),
        '|',
        ...input.slice(8), 0, 0, 0, 0, 0, 0 // padded
      ],
      bytes: [
        { hex: '0x' + hex(b0), label: 'count.lo', cls: 'header' },
        { hex: '0x' + hex(b1), label: 'count.hi|flags', cls: 'header' },
        ...payloadBytes.map(b => ({ hex: '0x' + hex(b), label: 'payload' }))
      ]
    },
    {
      commentary: 'Base64-encode the four bytes for a JSON-safe string. Total: header + payload = 4 bytes.',
      rows: [mkRow('input', input.map(String), 'dim')],
      bytes: [
        { hex: '0x' + hex(b0), label: 'hdr', cls: 'header' },
        { hex: '0x' + hex(b1), label: 'hdr', cls: 'header' },
        ...payloadBytes.map(b => ({ hex: '0x' + hex(b), label: 'pl' })),
        { hex: btoa(String.fromCharCode(b0, b1, ...payloadBytes)), label: 'base64', cls: 'b64' }
      ],
      meter: { orig: count + ' values × 1 B', encoded: '4 B', savedPct: '60 %' }
    }
  ];

  SCHEMES.push({
    code: 'bm',
    name: 'Bitmap',
    tagline: '0/1 lists → packed bits',
    blurb: 'For binary sequences only. A 2-byte header (count + a constant flag) followed by one bit per value, MSB-first. Constant-all-zero or all-one sequences need no payload at all.',
    frames
  });
})();

// ─── 7. BP — bit packing ───────────────────────────────────────────
(function () {
  const input = [5, 7, 6, 8, 5, 9, 6, 7];
  const lo = Math.min(...input);
  const hi = Math.max(...input);
  const shifted = input.map(v => v - lo);
  const range = hi - lo;
  const bpv = Math.max(1, Math.ceil(Math.log2(range + 1))); // 3
  // pack: for each value, push bpv bits MSB-first
  const bitsArr = [];
  shifted.forEach((v, idx) => {
    for (let b = bpv - 1; b >= 0; b--) bitsArr.push((v >> b) & 1);
    if (idx < shifted.length - 1) bitsArr.push('|');
  });
  // bytes: regroup the actual bits (without separators)
  const flatBits = bitsArr.filter(b => b !== '|');
  while (flatBits.length % 8) flatBits.push(0);
  const payloadBytes = [];
  for (let i = 0; i < flatBits.length; i += 8) {
    let byte = 0;
    for (let j = 0; j < 8; j++) byte = (byte << 1) | flatBits[i + j];
    payloadBytes.push(byte);
  }
  const hex = (n) => n.toString(16).toUpperCase().padStart(2, '0');

  const frames = [
    {
      commentary: `Input is ${input.length} integers, all in the range [${lo}, ${hi}]. Storing them as full ints (32 bits each) is grossly wasteful.`,
      rows: [mkRow('input', input.map(String))]
    },
    {
      commentary: `Find the range: <em>min</em>=${lo}, <em>max</em>=${hi}. That spans ${range + 1} distinct values — only ${bpv} bits required per value.`,
      rows: [mkRow('input', input.map(String), v => v == lo || v == hi ? 'hl' : '')],
      aux: [
        ['min',        String(lo),  'smallest input value. Becomes the <em>frame-of-reference</em> (FOR) offset, stored once in the binary header.'],
        ['max',        String(hi),  'largest input value; used to derive the bit width.'],
        ['bits/value', String(bpv), 'minimum bits required: <code>&lceil;log&#8322;(max &minus; min + 1)&rceil;</code>. Written into the 1-byte header.']
      ]
    },
    {
      commentary: `Apply <em>frame-of-reference</em>: subtract min from every value. Now everything fits in [0, ${range}].`,
      rows: [
        mkRow('input',   input.map(String), 'dim'),
        mkRow(`shifted (− ${lo})`, shifted.map(String), 'added')
      ],
      aux: [
        ['FOR.min',    String(lo),  'the offset subtracted from every value before packing. Stored as a signed varint in the header so the decoder can add it back.'],
        ['bits/value', String(bpv), 'fixed bit width used for every shifted value.']
      ]
    },
    {
      commentary: `Pack each shifted value as ${bpv} bits, MSB-first. Eight values × ${bpv} bits = ${input.length * bpv} bits = ${Math.ceil(input.length * bpv / 8)} bytes.`,
      rows: [
        mkRow('shifted', shifted.map(String), 'added')
      ],
      bits: bitsArr,
      aux: [
        ['FOR.min',    String(lo),  'subtracted offset, in the header.'],
        ['bits/value', String(bpv), 'each cluster of ' + bpv + ' bits above is one value.']
      ]
    },
    {
      commentary: `A 1-byte header carries bits/value, plus flags, count, and the FOR min. The whole thing base64-encodes for transport.`,
      rows: [mkRow('input', input.map(String), 'dim')],
      bytes: [
        { hex: '0x' + hex(bpv), label: 'bpv', cls: 'header' },
        { hex: '0x02',         label: 'flags', cls: 'header' },
        { hex: '0x' + hex(input.length), label: 'count', cls: 'header' },
        { hex: '0x' + hex(lo), label: 'FOR.min', cls: 'header' },
        ...payloadBytes.map(b => ({ hex: '0x' + hex(b), label: 'payload' })),
        { hex: btoa(String.fromCharCode(bpv, 2, input.length, lo, ...payloadBytes)),
          label: 'base64', cls: 'b64' }
      ],
      meter: { orig: `${input.length} × 1 B = ${input.length} B`,
               encoded: `${4 + payloadBytes.length} B`,
               savedPct: '—' }
    }
  ];

  SCHEMES.push({
    code: 'bp',
    name: 'Bit Packing',
    tagline: 'ints → minimum-width bit stream',
    blurb: 'The workhorse packer. Computes the minimum bit width from the range, applies frame-of-reference (FOR — subtract min), then writes values MSB-first. Almost every pipeline ends in <code>bp</code>.',
    frames
  });
})();

// ─── 8. NBP — nullmap bit-packing ──────────────────────────────────
(function () {
  const input = [0, 0, 5, 0, 0, 0, 7, 0, 0, 3];
  // dominant = 0 (count 7/10)
  const dom = 0;
  const nullmap = input.map(v => v === dom ? 0 : 1);
  const nonDom  = input.filter(v => v !== dom);   // [5, 7, 3]
  const lo = Math.min(...nonDom);                  // 3
  const shifted = nonDom.map(v => v - lo);         // [2, 4, 0]
  const range = Math.max(...shifted);
  const bpv = Math.max(1, Math.ceil(Math.log2(range + 1))); // 3

  const frames = [
    {
      commentary: 'A sparse sequence — most values are <em>0</em>; only a few are non-zero.',
      rows: [mkRow('input', input.map(String), v => v == 0 ? 'dom' : 'hl')]
    },
    {
      commentary: 'Identify the <em>dominant</em> value (the mode). Here <em>0</em> covers 7 of 10 positions.',
      rows: [mkRow('input', input.map(String), v => v == 0 ? 'dom' : 'hl')],
      aux: [
        ['dominant',  String(dom), 'the value that appears most often. Stored once in the binary blob and never repeated in the payload.'],
        ['dom_count', '7 / 10',    'how many positions equal the dominant. The higher this fraction, the more <code>nbp</code> saves.']
      ]
    },
    {
      commentary: 'Build a <em>nullmap</em>: one bit per position — <em>0</em> when the value equals the dominant, <em>1</em> otherwise.',
      rows: [
        mkRow('input',   input.map(String), v => v == 0 ? 'dom' : 'hl'),
        mkRow('nullmap', nullmap.map(String),
              (v, i) => v === 1 ? 'added' : 'dim')
      ],
      bits: nullmap
    },
    {
      commentary: `Collect the non-dominant values [${nonDom.join(', ')}], shift by their min (${lo}), then bit-pack with ${bpv} bits each.`,
      rows: [
        mkRow('non-dominant', nonDom.map(String), 'hl'),
        mkRow(`shifted (− ${lo})`, shifted.map(String), 'added')
      ],
      aux: [
        ['FOR.min',    String(lo),  'min of the <em>non-dominant</em> values. Subtracted before packing them.'],
        ['bits/value', String(bpv), 'bit width used for each non-dominant value after the FOR shift.']
      ]
    },
    {
      commentary: 'Final layout: [flags][count][dominant][bpv][FOR.min][nullmap][packed non-dominant values]. Hugely compact for sparse data.',
      rows: [mkRow('input', input.map(String), 'dim')],
      bits: [
        ...nullmap, '|',
        ...shifted.flatMap(v => {
          const bs = [];
          for (let b = bpv - 1; b >= 0; b--) bs.push((v >> b) & 1);
          return bs;
        })
      ],
      aux: [
        ['dominant', String(dom), 'the omnipresent value &mdash; written once.'],
        ['nullmap',  nullmap.join(''), '1 bit per position, MSB first. <em>0</em> = position equals the dominant, <em>1</em> = exception. Skipped entirely when all values are dominant.'],
        ['FOR.min',  String(lo),  'offset applied to the packed non-dominant values.'],
        ['bpv',      String(bpv), 'bits per non-dominant value after the FOR shift.']
      ],
      meter: { orig: `${input.length} × 1 B = ${input.length} B`, encoded: '≈ 6 B', savedPct: '40 %' }
    }
  ];

  SCHEMES.push({
    code: 'nbp',
    name: 'Nullmap Bit-Packing',
    tagline: 'sparse ints → nullmap + packed non-dominant',
    blurb: 'For sequences where one value dominates. Stores the dominant once, a 1-bit-per-element nullmap to mark exceptions, and a bit-packed list of just the non-dominant values.',
    frames
  });
})();


// ─── 9. TBQM — TurboQuant MSE ──────────────────────────────────────
(function () {
  // Simplified 4-dimensional illustration (real algo works on any d >= 3).
  const d = 4;
  const input = [0.60, -0.45, 0.52, -0.40];

  // Step 1: normalize
  const norm = Math.sqrt(input.reduce((s, v) => s + v * v, 0));
  const normalized = input.map(v => +(v / norm).toFixed(4));

  // Step 2: pretend rotation (for illustration, use a simple permutation)
  const rotated = [normalized[2], normalized[0], normalized[3], normalized[1]].map(v => +(v).toFixed(4));

  // Step 3: Lloyd-Max codebook with 2 bits (4 levels) — illustrative centroids
  const cb2 = [-0.84, -0.28, 0.28, 0.84];
  const indices = rotated.map(v => {
    let best = 0;
    let bestDist = Math.abs(v - cb2[0]);
    for (let k = 1; k < cb2.length; k++) {
      const dist = Math.abs(v - cb2[k]);
      if (dist < bestDist) { bestDist = dist; best = k; }
    }
    return best;
  });
  const quantized = indices.map(i => cb2[i]);

  // Step 4: bit-pack illustration — 2 bits × 4 values = 8 bits = 1 byte
  const bits = indices.flatMap(i => [(i >> 1) & 1, i & 1]);
  const byteVal = bits.reduce((acc, b, i) => acc | (b << (7 - i)), 0);
  const hex = n => n.toString(16).toUpperCase().padStart(2, '0');
  const b64 = btoa(String.fromCharCode(byteVal));

  const frames = [
    {
      commentary: `Input: a <em>${d}-dimensional float vector</em>. TurboQuant treats the whole list as one entity and quantizes it together.`,
      rows: [mkRow('input (d=' + d + ')', input.map(v => v.toFixed(2)))]
    },
    {
      commentary: 'Normalize to unit norm — all energy budgets become comparable. The original norm is saved for decoding.',
      rows: [
        mkRow('input', input.map(v => v.toFixed(2)), 'dim'),
        mkRow('normalized', normalized.map(String), 'added')
      ],
      aux: [
        ['tq_norm', norm.toFixed(4), 'original Euclidean norm — multiplied back during decode to restore scale.']
      ]
    },
    {
      commentary: 'Apply a seeded random orthogonal rotation (PCG64-based, platform-independent). This distributes the signal energy uniformly across all coordinates — after rotation, each coordinate has the same expected magnitude, so a single codebook is optimal for all of them.',
      rows: [
        mkRow('normalized', normalized.map(String), 'dim'),
        mkRow('rotated (Πx)', rotated.map(String), 'added')
      ],
      aux: [
        ['tq_seed', '42', 'determines the rotation matrix. Decoder uses the same seed to reconstruct Π and invert the rotation.']
      ]
    },
    {
      commentary: 'Quantize each rotated coordinate to the nearest entry in a Lloyd-Max codebook, optimized for the exact Beta distribution that arises after rotation.',
      rows: [
        mkRow('rotated', rotated.map(String)),
        mkRow('codebook index', indices.map(String), 'added')
      ],
      aux: [
        ['tq_bits', '2', 'bits per coordinate; here 2 bits → 4 codebook levels. A 4-bit codebook has 16 levels.']
      ]
    },
    {
      commentary: 'Pack all indices into a bitstream — ' + d + ' values × 2 bits = ' + (d * 2) + ' bits = 1 byte. Base64-encode for JSON transport.',
      rows: [mkRow('indices', indices.map(String), 'added')],
      bits: bits,
      bytes: [
        { hex: '0x' + hex(byteVal), label: 'packed' },
        { hex: b64, label: 'base64', cls: 'b64' }
      ],
      aux: [
        ['tq_dim',  String(d),             'dimension — decoder needs to know how many indices to unpack.'],
        ['tq_bits', '2',                   'bits per index.'],
        ['tq_seed', '42',                  'rotation seed.'],
        ['tq_norm', norm.toFixed(4),       'original norm — decoder multiplies by this after inverse-rotation.']
      ],
      meter: { orig: d + ' floats × ~4 B = ' + (d * 4) + ' B + aux', encoded: '1 B payload + 4 aux keys', savedPct: '—' }
    }
  ];

  SCHEMES.push({
    code: 'tbqm',
    name: 'TurboQuant MSE',
    tagline: 'float vector → rotation + codebook quantization (lossy)',
    blurb: 'Applies a random rotation to distribute signal energy uniformly, then quantizes each coordinate using a Lloyd-Max codebook optimal for the resulting Beta distribution. Near-optimal MSE for dense float vectors. Terminal — produces a base64 blob directly, no downstream packer needed. Requires vector length ≥ 3.',
    frames
  });
})();


// ─── 10. TBQP — TurboQuant Prod ────────────────────────────────────
(function () {
  const d = 4;
  const input = [0.60, -0.45, 0.52, -0.40];

  const norm = Math.sqrt(input.reduce((s, v) => s + v * v, 0));
  const normalized = input.map(v => +(v / norm).toFixed(4));

  // MSE step with 1 bit (2 levels) — mse_bits = num_bits - 1 = 2 - 1 = 1
  const rotated = [normalized[2], normalized[0], normalized[3], normalized[1]].map(v => +(v).toFixed(4));
  const cb1 = [-0.56, 0.56];  // 1-bit Lloyd-Max centroids (illustrative)
  const mseIdx = rotated.map(v => v >= 0 ? 1 : 0);
  const mseQuant = mseIdx.map(i => cb1[i]);

  // Residual (in normalized space)
  // inverse-rotate the quantized values back (simple permutation inverse)
  const invRotQuant = [mseQuant[1], mseQuant[3], mseQuant[0], mseQuant[2]];
  const residual = normalized.map((v, i) => +(v - invRotQuant[i]).toFixed(4));
  const resNorm = +Math.sqrt(residual.reduce((s, v) => s + v * v, 0)).toFixed(4);

  // QJL: sign of random projection of residual (illustrative)
  const qjlSigns = [1, -1, 1, 1];

  const frames = [
    {
      commentary: `Input: same <em>${d}-dimensional float vector</em>. TurboQuant Prod uses <em>num_bits−1</em> bits for MSE, reserving 1 bit per coordinate for a QJL residual correction that makes inner products unbiased.`,
      rows: [mkRow('input', input.map(v => v.toFixed(2)))]
    },
    {
      commentary: 'Stage 1 — run TurboQuant MSE with (num_bits−1) bits. Here total bits=2, so MSE uses 1 bit (2 codebook levels). This is coarser than standard tbqm.',
      rows: [
        mkRow('rotated (Πx)', rotated.map(String)),
        mkRow('1-bit MSE indices', mseIdx.map(String), 'added'),
        mkRow('quantized (ỹ_mse)', mseQuant.map(String), 'added')
      ],
      aux: [['tq_bits', '2', 'total bits. MSE stage uses tq_bits − 1 = 1 bit; the remaining 1 bit per coordinate goes to QJL.']]
    },
    {
      commentary: 'Stage 2 — compute the residual: r = x_normalized − x̃_mse. This is the signal the MSE stage missed.',
      rows: [
        mkRow('normalized', normalized.map(String), 'dim'),
        mkRow('x̃_mse (inverse-rotated)', invRotQuant.map(String), 'dim'),
        mkRow('residual r', residual.map(String), 'added')
      ],
      aux: [['tq_rnorm', String(resNorm), 'Euclidean norm of the residual — scales the QJL reconstruction.']]
    },
    {
      commentary: 'Apply QJL (Quantized Johnson-Lindenstrauss): project the residual with a random Gaussian matrix S, take only the sign. Each sign costs exactly 1 bit. The resulting inner-product estimator is unbiased: E[⟨x̃, ỹ⟩] = ⟨x, y⟩.',
      rows: [
        mkRow('residual r', residual.map(String), 'dim'),
        mkRow('sign(S · r)', qjlSigns.map(v => v > 0 ? '+1' : '−1'), 'added')
      ],
      aux: [
        ['tq_qseed', '43', 'seed for the random Gaussian projection matrix S. Decoder reconstructs the same S to undo the projection.'],
        ['tq_rnorm', String(resNorm), 'scales the QJL correction: x̃_qjl = (√π/2 / d) · ‖r‖ · Sᵀ · sign']
      ]
    },
    {
      commentary: 'Pack all three parts — [mse_indices][qjl_signs][residual_norm 8-byte float64] — into a single base64 blob.',
      rows: [
        mkRow('mse indices (1-bit)', mseIdx.map(String), 'added'),
        mkRow('qjl signs (1-bit each)', qjlSigns.map(v => v > 0 ? '+1' : '−1'), 'added')
      ],
      aux: [
        ['tq_dim',   String(d),      'vector dimension.'],
        ['tq_bits',  '2',            'total bits per coordinate.'],
        ['tq_seed',  '42',           'rotation seed.'],
        ['tq_norm',  norm.toFixed(4),'original vector norm.'],
        ['tq_rnorm', String(resNorm),'residual norm for QJL scaling.'],
        ['tq_qseed', '43',           'QJL projection seed.']
      ],
      meter: { orig: d + ' floats × ~4 B', encoded: 'mse + qjl + 8-byte norm + 6 aux keys', savedPct: '—' }
    }
  ];

  SCHEMES.push({
    code: 'tbqp',
    name: 'TurboQuant Prod',
    tagline: 'float vector → MSE + QJL residual (inner-product optimal, lossy)',
    blurb: 'Two-stage variant: TurboQuant MSE with (bits−1) bits, plus a 1-bit-per-coordinate QJL residual correction. The combination makes ⟨x̃, ỹ⟩ an <em>unbiased estimator</em> of ⟨x, y⟩ — better for cosine-similarity / dot-product downstream tasks at the same bit budget. Terminal step, requires vector length ≥ 3.',
    frames
  });
})();


// ─── player ────────────────────────────────────────────────────────
const players = [];

function buildSchemeSection(scheme, idx) {
  const sec = el('section', 'section sch-section');
  sec.id = 'sch-' + scheme.code;
  sec.innerHTML = `
    <div class="section-num">§ ${String(idx + 1).padStart(2, '0')}.</div>
    <h2 class="section-title">${esc(scheme.name)} <em>· <code>${esc(scheme.code)}</code></em></h2>
    <div class="section-body">
      <p class="sch-tagline">${scheme.tagline}</p>
      <p class="sch-blurb">${scheme.blurb}</p>

      <div class="sch-stage">
        <div class="sch-stage-head">
          <span class="sch-step-label">step</span>
          <span class="sch-step-name" data-role="name">—</span>
          <span class="sch-step-counter">
            <b data-role="cur">1</b> / <span data-role="total">${scheme.frames.length}</span>
          </span>
        </div>

        <div data-role="frame"></div>

        <div class="sch-controls">
          <button class="sch-btn" data-act="reset">⟲ reset</button>
          <button class="sch-btn" data-act="prev">◀ prev</button>
          <button class="sch-btn primary" data-act="play">▶ play</button>
          <button class="sch-btn" data-act="next">next ▶</button>
          <span class="sch-speed">
            speed
            <select data-role="speed">
              <option value="2400">slow</option>
              <option value="1500" selected>normal</option>
              <option value="800">fast</option>
            </select>
          </span>
        </div>
      </div>
    </div>
  `;

  const frameHost = $('[data-role="frame"]', sec);
  const nameEl    = $('[data-role="name"]', sec);
  const curEl     = $('[data-role="cur"]', sec);
  const speedEl   = $('[data-role="speed"]', sec);
  const playBtn   = $('[data-act="play"]', sec);

  const state = {
    scheme,
    i: 0,
    playing: false,
    timer: null,
    speed: 1500
  };

  function render() {
    const f = scheme.frames[state.i];
    frameHost.innerHTML = renderFrame(f);
    nameEl.innerHTML    = `frame ${state.i + 1} <em>·</em> ${stepName(state.i, scheme.frames.length)}`;
    curEl.textContent   = state.i + 1;
  }

  function step(delta) {
    state.i = Math.max(0, Math.min(scheme.frames.length - 1, state.i + delta));
    if (state.i === scheme.frames.length - 1 && state.playing) pause();
    render();
  }

  function play() {
    if (state.i >= scheme.frames.length - 1) state.i = 0;
    state.playing = true;
    playBtn.textContent = '❚❚ pause';
    state.timer = setInterval(() => {
      if (state.i >= scheme.frames.length - 1) { pause(); return; }
      step(1);
    }, state.speed);
  }
  function pause() {
    state.playing = false;
    playBtn.textContent = '▶ play';
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
  }
  function reset() { pause(); state.i = 0; render(); }

  sec.addEventListener('click', (ev) => {
    const act = ev.target.closest('[data-act]')?.dataset.act;
    if (!act) return;
    if (act === 'play')  state.playing ? pause() : play();
    if (act === 'prev')  { pause(); step(-1); }
    if (act === 'next')  { pause(); step(1); }
    if (act === 'reset') reset();
  });
  speedEl.addEventListener('change', () => {
    state.speed = Number(speedEl.value);
    if (state.playing) { pause(); play(); }
  });

  render();
  players.push(state);
  return sec;
}

function stepName(i, total) {
  if (i === 0) return 'input';
  if (i === total - 1) return 'encoded';
  return 'transformation ' + i;
}

// ─── boot ──────────────────────────────────────────────────────────
function boot() {
  // index strip
  const ix = $('#schIndex');
  ix.innerHTML = SCHEMES.map((s, i) => `
    <a href="#sch-${s.code}">
      <span class="ix-code">${esc(s.code)}</span>
      <span class="ix-name">${esc(s.name)}</span>
    </a>
  `).join('');

  // sections
  const host = $('#schemeSections');
  SCHEMES.forEach((s, i) => host.appendChild(buildSchemeSection(s, i)));

  // date
  const d = new Date();
  const months = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
  const dateStr = $('#dateStr');
  if (dateStr) dateStr.textContent = `${months[d.getMonth()]} ${d.getFullYear()}`;
}

document.addEventListener('DOMContentLoaded', boot);

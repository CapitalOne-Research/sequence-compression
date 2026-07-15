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
  const connect = () => { if (canvas.length) canvas.push(`<div class="sch-arrow">↓</div>`); };
  (frame.rows || []).forEach((row) => {
    connect();
    canvas.push(rowHTML(row));
  });
  if (frame.bits)  { connect(); canvas.push(bitsHTML(frame.bits)); }
  if (frame.bytes) { connect(); canvas.push(bytesHTML(frame.bytes)); }
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

  const itos = { 0: 'WEB', 1: 'MOBILE', 2: 'TABLET' };
  const decodeFrames = [
    {
      commentary: 'Decode starts from the integer ids plus the stored <code>stoi</code> dictionary.',
      rows: [mkRow('encoded', encoded.map(String))],
      aux: [['stoi', '{WEB:0, MOBILE:1, TABLET:2}', 'the dictionary saved at encode time &mdash; everything the decoder needs to invert the mapping.']]
    },
    {
      commentary: 'Flip the dictionary to build <em>itos</em>: id &rarr; label.',
      rows: [mkRow('encoded', encoded.map(String))],
      aux: [
        ['itos.0', itos[0], 'inverse of <code>stoi</code>, built once by swapping keys and values.'],
        ['itos.1', itos[1], 'id 1 maps back to MOBILE.'],
        ['itos.2', itos[2], 'id 2 maps back to TABLET.']
      ]
    },
    {
      commentary: 'Substitute each id with its label. The original strings return exactly &mdash; <code>cat</code> is lossless.',
      rows: [
        mkRow('encoded', encoded.map(String), 'dim'),
        mkRow('decoded', encoded.map(v => itos[v]), 'added')
      ]
    }
  ];

  SCHEMES.push({
    decodeFrames,
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

  const recon = q.map(v => +(v * scale + lo).toFixed(2));
  const decodeFrames = [
    {
      commentary: 'Decode reads the quantized ints plus the affine parameters.',
      rows: [mkRow('q (int)', q.map(String))],
      aux: [
        ['q_scale', scale.toFixed(4), 'step size to multiply back.'],
        ['min',     lo.toFixed(2),    'lower edge added after scaling to undo the shift.']
      ]
    },
    {
      commentary: `Reconstruct with <code>x &asymp; q &middot; scale + min</code>. Quantization is <em>lossy</em> &mdash; each value lands within &frac12;&middot;scale of the original.`,
      rows: [
        mkRow('q (int)',   q.map(String), 'dim'),
        mkRow('x̃ (float)', recon.map(v => v.toFixed(2)), 'added'),
        mkRow('original',  input.map(v => v.toFixed(2)), 'dim')
      ]
    }
  ];

  SCHEMES.push({
    decodeFrames,
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

  const recon = [v0];
  deltas.forEach(d => recon.push(recon[recon.length - 1] + d));
  const decodeFrames = [
    {
      commentary: 'Decode starts from <em>v₀</em> and the delta stream.',
      rows: [mkRow('deltas (Δ)', deltas.map(d => (d >= 0 ? '+' : '') + d))],
      aux: [['v0', String(v0), 'the saved starting value &mdash; the anchor for the running sum.']]
    },
    {
      commentary: 'Seed the output with <em>v₀</em>, then walk left-to-right, adding each delta to the previous result.',
      rows: [
        mkRow('deltas (Δ)',  deltas.map(d => (d >= 0 ? '+' : '') + d), 'dim'),
        mkRow('running sum', recon.map(String), (v, i) => i === 0 ? 'hl' : 'added')
      ]
    },
    {
      commentary: 'The prefix sum <code>xᵢ = v0 + Σ Δ</code> restores the absolute sequence exactly &mdash; <code>del</code> is lossless.',
      rows: [
        mkRow('deltas (Δ)', deltas.map(d => (d >= 0 ? '+' : '') + d), 'dim'),
        mkRow('decoded',    recon.map(String), 'added')
      ]
    }
  ];

  SCHEMES.push({
    decodeFrames,
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

  const expanded = runs.reduce((a, [v, c]) => a.concat(Array(c).fill(v)), []);
  const decodeFrames = [
    {
      commentary: 'Decode reads the flat <em>[value, count, …]</em> stream.',
      rows: [mkRow('encoded', flat)]
    },
    {
      commentary: 'Take the first pair <code>[A, 3]</code> — emit <em>A</em> three times.',
      rows: [
        mkRow('encoded',  flat, (v, i) => i < 2 ? 'hl' : 'dim'),
        mkRow('expanded', ['A', 'A', 'A'], 'added')
      ]
    },
    {
      commentary: 'Expand every remaining pair the same way. The original sequence returns exactly &mdash; <code>rle</code> is lossless.',
      rows: [
        mkRow('encoded', flat, 'dim'),
        mkRow('decoded', expanded, 'added')
      ]
    }
  ];

  SCHEMES.push({
    decodeFrames,
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

  const recon = [];
  {
    let ci = 0;
    for (let i = 0; i < input.length; i++) {
      recon.push(positions.includes(i) ? 0 : clean[ci++]);
    }
  }
  const decodeFrames = [
    {
      commentary: 'Decode has the clean values, the sentinel positions, and the original length.',
      rows: [mkRow('clean', clean.map(String))],
      aux: [
        ['snt_ranges', `{0: [[${positions[0]}], [${positions[1]}]]}`, 'where each stripped sentinel belongs in the output.'],
        ['length',     String(input.length), 'how many slots to rebuild &mdash; the clean list is shorter.']
      ]
    },
    {
      commentary: `Allocate <em>length</em> slots and drop the sentinel <em>0</em> back at positions ${positions.join(' and ')}.`,
      rows: [mkRow('slots', input.map((v, i) => positions.includes(i) ? '0' : '·'),
                   (v, i) => positions.includes(i) ? 'sentinel' : 'dim')]
    },
    {
      commentary: 'Fill the remaining slots from the clean stream in order. Original sequence restored &mdash; <code>stl</code> is lossless.',
      rows: [
        mkRow('clean',   clean.map(String), 'dim'),
        mkRow('decoded', recon.map(String), (v, i) => positions.includes(i) ? 'sentinel' : 'added')
      ]
    }
  ];

  SCHEMES.push({
    decodeFrames,
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

  const decodeFrames = [
    {
      commentary: 'Decode base64 → bytes, then read the 2-byte header for <em>count</em>.',
      bytes: [
        { hex: '0x' + hex(b0), label: 'count.lo', cls: 'header' },
        { hex: '0x' + hex(b1), label: 'count.hi|flags', cls: 'header' }
      ],
      aux: [
        ['count',         String(count), 'number of bits to pull out of the payload.'],
        ['constant_flag', '0',           'not set, so a real payload follows (a set flag would mean one repeated bit, no payload).']
      ]
    },
    {
      commentary: 'Unpack the payload bytes back into bits, MSB-first.',
      bits: [
        ...input.slice(0, 8),
        '|',
        ...input.slice(8), 0, 0, 0, 0, 0, 0
      ],
      aux: [['count', String(count), 'the trailing 6 padding bits are discarded.']]
    },
    {
      commentary: 'Keep the first <em>' + count + '</em> bits and drop the padding. Bitmap is lossless.',
      rows: [mkRow('decoded', input.map(String), v => v === 1 ? 'hl' : 'dim')]
    }
  ];

  SCHEMES.push({
    decodeFrames,
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

  const decodeFrames = [
    {
      commentary: 'Decode reads the 1-byte header: bits/value, count, and the FOR min.',
      bytes: [
        { hex: '0x' + hex(bpv), label: 'bpv', cls: 'header' },
        { hex: '0x02',          label: 'flags', cls: 'header' },
        { hex: '0x' + hex(input.length), label: 'count', cls: 'header' },
        { hex: '0x' + hex(lo),  label: 'FOR.min', cls: 'header' }
      ],
      aux: [
        ['bits/value', String(bpv), 'width of each packed cluster to read.'],
        ['FOR.min',    String(lo),  'offset to add back after unpacking.']
      ]
    },
    {
      commentary: `Read the payload in ${bpv}-bit clusters, MSB-first — one cluster per value.`,
      bits: bitsArr,
      aux: [['bits/value', String(bpv), 'each highlighted cluster becomes one shifted value.']]
    },
    {
      commentary: `Each cluster is a shifted value; add <em>FOR.min = ${lo}</em> back to every one. Original ints restored exactly — <code>bp</code> is lossless.`,
      rows: [
        mkRow('shifted',           shifted.map(String), 'dim'),
        mkRow(`decoded (+ ${lo})`, input.map(String), 'added')
      ]
    }
  ];

  SCHEMES.push({
    decodeFrames,
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

  const decodeFrames = [
    {
      commentary: 'Decode reads the dominant value, the nullmap, and the packed non-dominant values.',
      bits: [
        ...nullmap, '|',
        ...shifted.flatMap(v => {
          const bs = [];
          for (let b = bpv - 1; b >= 0; b--) bs.push((v >> b) & 1);
          return bs;
        })
      ],
      aux: [
        ['dominant', String(dom),      'fills every position the nullmap marks 0.'],
        ['nullmap',  nullmap.join(''), '1 bit per output position, read MSB-first.']
      ]
    },
    {
      commentary: `Unpack the non-dominant values (${bpv} bits each) and undo their FOR shift by adding <em>${lo}</em>.`,
      rows: [
        mkRow('shifted',              shifted.map(String), 'dim'),
        mkRow(`non-dominant (+ ${lo})`, nonDom.map(String), 'added')
      ]
    },
    {
      commentary: 'Walk the nullmap: a <em>0</em> emits the dominant value, a <em>1</em> pulls the next non-dominant value. Lossless.',
      rows: [
        mkRow('nullmap', nullmap.map(String), v => v === 1 ? 'hl' : 'dim'),
        mkRow('decoded', input.map(String), (v, i) => nullmap[i] === 1 ? 'added' : 'dom')
      ]
    }
  ];

  SCHEMES.push({
    decodeFrames,
    code: 'nbp',
    name: 'Nullmap Bit-Packing',
    tagline: 'sparse ints → nullmap + packed non-dominant',
    blurb: 'For sequences where one value dominates. Stores the dominant once, a 1-bit-per-element nullmap to mark exceptions, and a bit-packed list of just the non-dominant values.',
    frames
  });
})();


// ─── 9. TBQM — TurboQuant MSE ──────────────────────────────────────
(function () {
  // 16-dimensional illustration (real algo works on any d >= 3).
  const d = 16;
  const input = [0.60, -0.45, 0.52, -0.40, 0.31, -0.72, 0.18, 0.63,
                 -0.55, 0.22, -0.38, 0.47, 0.29, -0.61, 0.43, -0.15];

  // Step 1: normalize
  const norm = +Math.sqrt(input.reduce((s, v) => s + v * v, 0)).toFixed(4);
  const normalized = input.map(v => +(v / norm).toFixed(4));

  // Step 2: seeded rotation — illustrated as a cyclic permutation (+7 mod 16)
  const perm = Array.from({ length: d }, (_, i) => (i + 7) % d);
  const rotated = perm.map(p => normalized[p]);

  // Step 3: Lloyd-Max codebook with 4 bits (16 levels); illustrative uniform grid
  const nbits = 4;
  const levels = 1 << nbits;
  const cb = Array.from({ length: levels }, (_, k) => +(-0.75 + 1.5 * k / (levels - 1)).toFixed(4));
  const indices = rotated.map(v => {
    let best = 0;
    let bestDist = Math.abs(v - cb[0]);
    for (let k = 1; k < cb.length; k++) {
      const dist = Math.abs(v - cb[k]);
      if (dist < bestDist) { bestDist = dist; best = k; }
    }
    return best;
  });
  const quantized = indices.map(i => cb[i]);

  // Inverse permutation: perm[i] = (i+7)%d  →  inv[j] = (j+9)%d
  const invPerm = Array.from({ length: d }, (_, j) => (j + 9) % d);
  const invRotQuant = invPerm.map(p => quantized[p]);
  const reconstructed = invRotQuant.map(v => +(v * norm).toFixed(2));

  const frames = [
    {
      commentary: `Input: a <em>${d}-dimensional float vector</em> (e.g. a reduced embedding). TurboQuant treats the whole list as one entity and quantizes it together.`,
      rows: [mkRow('input (d=' + d + ')', input.map(v => v.toFixed(2)))]
    },
    {
      commentary: 'Normalize to unit norm — all energy budgets become comparable. The original norm is saved for decoding.',
      rows: [
        mkRow('input', input.map(v => v.toFixed(2)), 'dim'),
        mkRow('normalized', normalized.map(String), 'added')
      ],
      aux: [
        ['tq_norm', String(norm), 'original Euclidean norm — multiplied back during decode to restore scale.']
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
        ['tq_bits', String(nbits), 'bits per coordinate; here ' + nbits + ' bits → ' + levels + ' codebook levels. Fewer bits mean a coarser grid and higher loss.']
      ]
    },
    {
      commentary: 'The output is a plain list of ' + d + ' codebook indices in [0, ' + (levels - 1) + ']. There is no bit-packing here: <code>tbqm</code> is composable, so a downstream <code>bp</code> stage (the pipeline <code>tbqm_bp</code>) does the final bit-level squeeze — ' + d + ' × ' + nbits + ' bits = ' + (d * nbits / 8) + ' B payload, versus ' + (d * 4) + ' B for ' + d + ' float32 values.',
      rows: [mkRow('indices', indices.map(String), 'added')],
      aux: [
        ['tq_dim',  String(d),     'dimension, so the decoder knows how many indices to read.'],
        ['tq_bits', String(nbits), 'bits per index; here ' + nbits + ' bits, so ' + levels + ' codebook levels.'],
        ['tq_seed', '42',          'rotation seed.'],
        ['tq_norm', String(norm),  'original norm, multiplied back after inverse-rotation.']
      ],
      meter: { orig: d + ' float32 = ' + (d * 4) + ' B', encoded: (d * nbits / 8) + ' B packed (tbqm_bp)', savedPct: '84 %' }
    }
  ];

  const decodeFrames = [
    {
      commentary: 'Decode starts from the plain index list plus the aux parameters. When composed as <code>tbqm_bp</code>, the downstream packer has already unpacked these ints.',
      rows: [mkRow('indices', indices.map(String))],
      aux: [
        ['tq_dim',  String(d),     'how many indices to read back.'],
        ['tq_bits', String(nbits), 'bits per index, so the codebook has ' + levels + ' levels.']
      ]
    },
    {
      commentary: 'Look up each index in the same Lloyd-Max codebook to recover the rotated estimate.',
      rows: [
        mkRow('indices',        indices.map(String), 'dim'),
        mkRow('codebook value', quantized.map(String), 'added')
      ]
    },
    {
      commentary: 'Invert the rotation with the stored seed, then rescale by the saved norm. TurboQuant is <em>lossy</em>, so the estimate is close, not exact.',
      rows: [
        mkRow('rotated est.',    quantized.map(String), 'dim'),
        mkRow('inverse-rotated', invRotQuant.map(String), 'dim'),
        mkRow('x̃ (× norm)',      reconstructed.map(v => v.toFixed(2)), 'added'),
        mkRow('original',        input.map(v => v.toFixed(2)), 'dim')
      ],
      aux: [
        ['tq_seed', '42',       'rebuilds the same rotation matrix Π so it can be inverted.'],
        ['tq_norm', String(norm), 'multiplied back to restore the original scale.']
      ]
    }
  ];

  SCHEMES.push({
    decodeFrames,
    code: 'tbqm',
    name: 'TurboQuant MSE',
    tagline: 'float vector → rotation + codebook quantization (lossy)',
    blurb: 'Applies a random rotation to distribute signal energy uniformly, then quantizes each coordinate using a Lloyd-Max codebook optimal for the resulting Beta distribution. Near-optimal MSE for dense float vectors. Emits a plain list of codebook indices, so it stays composable: a downstream packer (e.g. <code>tbqm_bp</code>) does the final bit-level squeeze. Requires vector length ≥ 3.',
    frames
  });
})();


// ─── 10. TBQP — TurboQuant Prod ────────────────────────────────────
(function () {
  const d = 16;
  const input = [0.60, -0.45, 0.52, -0.40, 0.31, -0.72, 0.18, 0.63,
                 -0.55, 0.22, -0.38, 0.47, 0.29, -0.61, 0.43, -0.15];

  const norm = +Math.sqrt(input.reduce((s, v) => s + v * v, 0)).toFixed(4);
  const normalized = input.map(v => +(v / norm).toFixed(4));

  // Same seeded rotation as tbqm (+7 mod 16 cyclic permutation)
  const perm    = Array.from({ length: d }, (_, i) => (i + 7) % d);
  const invPerm = Array.from({ length: d }, (_, j) => (j + 9) % d);
  const rotated = perm.map(p => normalized[p]);

  // MSE step with 3 bits (8 levels): mse_bits = num_bits - 1 = 4 - 1 = 3
  const cbMse = [-0.7, -0.5, -0.3, -0.1, 0.1, 0.3, 0.5, 0.7];  // 3-bit codebook (illustrative)
  const mseIdx = rotated.map(v => {
    let best = 0;
    let bestDist = Math.abs(v - cbMse[0]);
    for (let k = 1; k < cbMse.length; k++) {
      const dist = Math.abs(v - cbMse[k]);
      if (dist < bestDist) { bestDist = dist; best = k; }
    }
    return best;
  });
  const mseQuant = mseIdx.map(i => cbMse[i]);

  // Residual (in normalized space): inverse-rotate mse quant back, then subtract
  const invRotMse = invPerm.map(p => mseQuant[p]);
  const residual  = normalized.map((v, i) => +(v - invRotMse[i]).toFixed(4));
  const resNorm   = +Math.sqrt(residual.reduce((s, v) => s + v * v, 0)).toFixed(4);

  // QJL: sign of random projection of residual (illustrated as sign of residual itself)
  const qjlSigns = residual.map(r => r >= 0 ? 1 : -1);

  // Packed bit budget: 16 × 3-bit MSE + 16 × 1-bit QJL = 64 bits = 8 B + 2 B header = 10 B
  const totalBits  = d * 3 + d * 1;
  const packedB    = Math.ceil(totalBits / 8) + 2;

  const frames = [
    {
      commentary: `Input: same <em>${d}-dimensional float vector</em>. TurboQuant Prod uses <em>num_bits−1</em> bits for MSE, reserving 1 bit per coordinate for a QJL residual correction that makes inner products unbiased.`,
      rows: [mkRow('input', input.map(v => v.toFixed(2)))]
    },
    {
      commentary: 'Stage 1 — run TurboQuant MSE with (num_bits−1) bits. Here total bits=4, so MSE uses 3 bits (8 codebook levels), leaving the last bit per coordinate for QJL.',
      rows: [
        mkRow('rotated (Πx)',      rotated.map(String)),
        mkRow('3-bit MSE indices', mseIdx.map(String), 'added'),
        mkRow('quantized (ỹ_mse)', mseQuant.map(String), 'added')
      ],
      aux: [['tq_bits', '4', 'total bits. MSE stage uses tq_bits − 1 = 3 bits; the remaining 1 bit per coordinate goes to QJL.']]
    },
    {
      commentary: 'Stage 2 — compute the residual: r = x_normalized − x̃_mse. This is the signal the MSE stage missed.',
      rows: [
        mkRow('normalized',              normalized.map(String), 'dim'),
        mkRow('x̃_mse (inverse-rotated)', invRotMse.map(String), 'dim'),
        mkRow('residual r',              residual.map(String), 'added')
      ],
      aux: [['tq_rnorm', String(resNorm), 'Euclidean norm of the residual — scales the QJL reconstruction.']]
    },
    {
      commentary: 'Apply QJL (Quantized Johnson-Lindenstrauss): project the residual with a random Gaussian matrix S, take only the sign. Each sign costs exactly 1 bit. The resulting inner-product estimator is unbiased: E[⟨x̃, ỹ⟩] = ⟨x, y⟩.',
      rows: [
        mkRow('residual r',  residual.map(String), 'dim'),
        mkRow('sign(S · r)', qjlSigns.map(v => v > 0 ? '+1' : '−1'), 'added')
      ],
      aux: [
        ['tq_qseed', '43',           'seed for the random Gaussian projection matrix S. Decoder reconstructs the same S to undo the projection.'],
        ['tq_rnorm', String(resNorm), 'scales the QJL correction: x̃_qjl = (√π/2 / d) · ‖r‖ · Sᵀ · sign']
      ]
    },
    {
      commentary: 'Output: ' + d + ' MSE indices (3-bit each) plus 16 QJL sign bits. When packed as <code>tbqp_bp</code>: ' + d + '×3 + ' + d + '×1 = ' + totalBits + ' bits = ' + (totalBits / 8) + ' B payload + 2 B header. Same wire size as <code>tbqm_bp</code>, but inner-product unbiased.',
      rows: [
        mkRow('mse indices (3-bit)', mseIdx.map(String), 'added')
      ],
      aux: [
        ['tq_dim',   String(d),                                    'vector dimension.'],
        ['tq_bits',  '4',                                          'total bits per coordinate.'],
        ['tq_seed',  '42',                                         'rotation seed.'],
        ['tq_norm',  String(norm),                                 'original vector norm.'],
        ['tq_rnorm', String(resNorm),                              'residual norm for QJL scaling.'],
        ['tq_qseed', '43',                                         'QJL projection seed.'],
        ['tq_signs', qjlSigns.map(v => v > 0 ? 1 : 0).join(''),   'the QJL sign bits (mapped +1 to 1, −1 to 0), bitmap-encoded into a compact string.']
      ],
      meter: { orig: d + ' float32 = ' + (d * 4) + ' B', encoded: packedB + ' B packed (tbqp_bp)', savedPct: '84 %' }
    }
  ];

  const factor        = Math.sqrt(Math.PI / 2) / d * resNorm;
  const qjlCorr       = qjlSigns.map(s => +(factor * s).toFixed(4));
  const normEst       = invRotMse.map((v, i) => +(v + qjlCorr[i]).toFixed(4));
  const reconstructed = normEst.map(v => +(v * norm).toFixed(2));
  const decodeFrames = [
    {
      commentary: 'Decode starts from the MSE index list. The QJL signs are recovered from aux (<code>tq_signs</code>, bitmap-decoded back to ±1), along with both norms.',
      rows: [
        mkRow('mse indices',               mseIdx.map(String)),
        mkRow('qjl signs (from tq_signs)', qjlSigns.map(v => v > 0 ? '+1' : '−1'), 'dim')
      ],
      aux: [
        ['tq_signs', qjlSigns.map(v => v > 0 ? 1 : 0).join(''), 'the QJL sign bits, bitmap-decoded back to ±1.'],
        ['tq_norm',  String(norm),   'restores overall scale at the very end.'],
        ['tq_rnorm', String(resNorm), 'scales the QJL residual correction.']
      ]
    },
    {
      commentary: 'Stage 1 — rebuild the MSE estimate from the 3-bit indices, then inverse-rotate it back into normalized space.',
      rows: [
        mkRow('mse indices',             mseIdx.map(String), 'dim'),
        mkRow('x̃_mse (rotated)',         mseQuant.map(String), 'added'),
        mkRow('x̃_mse (inverse-rotated)', invRotMse.map(String), 'added')
      ]
    },
    {
      commentary: 'Stage 2 — rebuild the projection matrix S from <code>tq_qseed</code> and add the QJL correction <code>(√π/2 / d)·‖r‖·Sᵀ·sign</code>.',
      rows: [
        mkRow('x̃_mse',          invRotMse.map(String), 'dim'),
        mkRow('qjl correction', qjlCorr.map(v => (v >= 0 ? '+' : '') + v), 'added'),
        mkRow('x̃ (normalized)', normEst.map(String), 'added')
      ],
      aux: [['tq_qseed', '43', 'reconstructs the same Gaussian projection S used at encode time.']]
    },
    {
      commentary: 'Rescale by the saved norm. The result is <em>lossy</em> per element, but ⟨x̃, ỹ⟩ is an <em>unbiased</em> estimate of the true inner product — the property TurboQuant Prod optimizes for.',
      rows: [
        mkRow('x̃ (× norm)', reconstructed.map(v => v.toFixed(2)), 'added'),
        mkRow('original',   input.map(v => v.toFixed(2)), 'dim')
      ]
    }
  ];

  SCHEMES.push({
    decodeFrames,
    code: 'tbqp',
    name: 'TurboQuant Prod',
    tagline: 'float vector → MSE + QJL residual (inner-product optimal, lossy)',
    blurb: 'Two-stage variant: TurboQuant MSE with (bits−1) bits, plus a 1-bit-per-coordinate QJL residual correction. The combination makes ⟨x̃, ỹ⟩ an <em>unbiased estimator</em> of ⟨x, y⟩, better for cosine-similarity / dot-product downstream tasks at the same bit budget. Emits a plain list of MSE indices (the QJL signs ride along in aux) and stays composable with a downstream packer. Requires vector length ≥ 3.',
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
          <div class="sch-phases" data-role="phases">
            <button class="sch-phase-seg encode active" data-jump="encode">
              <span class="seg-label">encode</span>
              <span class="seg-count">${scheme.frames.length}</span>
            </button>
            <span class="sch-phase-arrow">→</span>
            <button class="sch-phase-seg decode" data-jump="decode">
              <span class="seg-label">decode</span>
              <span class="seg-count">${(scheme.decodeFrames || []).length}</span>
            </button>
          </div>
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
  const totalEl   = $('[data-role="total"]', sec);
  const segEncode = $('[data-jump="encode"]', sec);
  const segDecode = $('[data-jump="decode"]', sec);
  const speedEl   = $('[data-role="speed"]', sec);
  const playBtn   = $('[data-act="play"]', sec);

  // encode frames, then the decode walk-back, played through one continuous timeline
  const encFrames = scheme.frames;
  const decFrames = scheme.decodeFrames || [];
  const allFrames = encFrames.concat(decFrames);

  const state = {
    scheme,
    i: 0,
    playing: false,
    timer: null,
    speed: 1500
  };

  function render() {
    const f = allFrames[state.i];
    frameHost.innerHTML = renderFrame(f);
    const inDecode    = state.i >= encFrames.length;
    const phaseFrames = inDecode ? decFrames.length : encFrames.length;
    const localI      = inDecode ? state.i - encFrames.length : state.i;
    segEncode.classList.toggle('active', !inDecode);
    segDecode.classList.toggle('active', inDecode);
    // pulse the decode tab once encode finishes, to surface the walk-back
    segDecode.classList.toggle('hint',
      !inDecode && localI === encFrames.length - 1 && decFrames.length > 0);
    nameEl.innerHTML  = stepName(localI, phaseFrames, inDecode);
    curEl.textContent = localI + 1;
    totalEl.textContent = phaseFrames;
  }

  function step(delta) {
    state.i = Math.max(0, Math.min(allFrames.length - 1, state.i + delta));
    if (state.i === allFrames.length - 1 && state.playing) pause();
    render();
  }

  function play() {
    if (state.i >= allFrames.length - 1) state.i = 0;
    state.playing = true;
    playBtn.textContent = '❚❚ pause';
    state.timer = setInterval(() => {
      if (state.i >= allFrames.length - 1) { pause(); return; }
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
    const jump = ev.target.closest('[data-jump]')?.dataset.jump;
    if (jump) {
      pause();
      state.i = (jump === 'decode' && decFrames.length) ? encFrames.length : 0;
      render();
      return;
    }
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

function stepName(i, total, decode) {
  if (!decode) {
    if (i === 0) return 'input';
    if (i === total - 1) return 'encoded';
    return 'transformation ' + i;
  }
  if (i === 0) return 'encoded record';
  if (i === total - 1) return 'restored';
  return 'inverse ' + i;
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

/**
 * Text normalisation, fuzzy matching and unit parsing.
 *
 * A direct port of labelcheck/textnorm.py. The Python version remains the
 * reference implementation with its own test suite; tests/parity.mjs checks
 * that this port agrees with it, because two copies of compliance logic that
 * quietly disagree would be worse than having only one.
 */

export const ML_PER_FL_OZ = 29.5735295625;
export const ML_PER_PINT = 473.176473;
export const ML_PER_QUART = 946.352946;
export const ML_PER_GALLON = 3785.411784;

// Characters OCR commonly substitutes inside numbers.
const DIGIT_FIXES = {
  O: '0', o: '0', Q: '0', D: '0',
  l: '1', I: '1', '|': '1', i: '1',
  S: '5', s: '5', B: '8', Z: '2', z: '2', G: '6',
};

const COMPANY_STOPWORDS = new Set([
  'the', 'and', 'co', 'company', 'inc', 'incorporated', 'llc', 'llp', 'lp',
  'ltd', 'limited', 'corp', 'corporation', 'gmbh', 'sa', 'sas', 'spa',
  'srl', 'bv', 'nv', 'ag', 'pty', 'plc', 'of',
]);

export function stripAccents(value) {
  return String(value).normalize('NFKD').replace(/[̀-ͯ]/g, '');
}

export function normalize(value) {
  if (!value) return '';
  let text = stripAccents(String(value));
  text = text.replace(/&/g, ' and ');
  text = text.replace(/[^\w\s%./-]+/g, ' ');
  text = text.replace(/-/g, ' ').replace(/\//g, ' ').replace(/\./g, ' ');
  text = text.replace(/\s+/g, ' ');
  return text.trim().toLowerCase();
}

export function tokens(value) {
  const n = normalize(value);
  return n ? n.split(' ') : [];
}

export function significantTokens(value) {
  return tokens(value).filter((t) => !COMPANY_STOPWORDS.has(t));
}

/* ---- difflib.SequenceMatcher.ratio(), ported ---------------------------
 * Python's difflib uses the Ratcliff/Obershelp algorithm, not edit
 * distance. Substituting a Levenshtein ratio here would shift every
 * matching threshold, so the real algorithm is reproduced.
 */
function buildB2J(b) {
  const b2j = new Map();
  for (let i = 0; i < b.length; i += 1) {
    const ch = b[i];
    let list = b2j.get(ch);
    if (!list) { list = []; b2j.set(ch, list); }
    list.push(i);
  }
  return b2j;
}

function findLongestMatch(a, b2j, alo, ahi, blo, bhi) {
  let besti = alo;
  let bestj = blo;
  let bestsize = 0;
  let j2len = new Map();
  for (let i = alo; i < ahi; i += 1) {
    const newj2len = new Map();
    const positions = b2j.get(a[i]);
    if (positions) {
      for (const j of positions) {
        if (j < blo) continue;
        if (j >= bhi) break;
        const k = (j2len.get(j - 1) || 0) + 1;
        newj2len.set(j, k);
        if (k > bestsize) { besti = i - k + 1; bestj = j - k + 1; bestsize = k; }
      }
    }
    j2len = newj2len;
  }
  return [besti, bestj, bestsize];
}

function matchingTotal(a, b) {
  const b2j = buildB2J(b);
  let total = 0;
  const queue = [[0, a.length, 0, b.length]];
  while (queue.length) {
    const [alo, ahi, blo, bhi] = queue.pop();
    const [i, j, k] = findLongestMatch(a, b2j, alo, ahi, blo, bhi);
    if (k) {
      total += k;
      if (alo < i && blo < j) queue.push([alo, i, blo, j]);
      if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
    }
  }
  return total;
}

export function similarity(a, b) {
  if (!a || !b) return 0;
  if (a === b) return 1;
  const total = a.length + b.length;
  if (!total) return 1;
  return (2 * matchingTotal(a, b)) / total;
}

/** Best similarity between `needle` and any same-length run of `haystack`. */
export function bestWindowSimilarity(needle, haystack) {
  const needleN = normalize(needle);
  const hayN = normalize(haystack);
  if (!needleN || !hayN) return 0;
  if (hayN.includes(needleN)) return 1;

  const needleWords = needleN.split(' ');
  const hayWords = hayN.split(' ');
  if (!needleWords.length || !hayWords.length) return 0;

  const span = needleWords.length;
  let best = similarity(needleN, hayN);
  const widths = new Set([Math.max(1, span - 1), span, span + 1]);
  for (const width of widths) {
    if (width > hayWords.length) continue;
    for (let start = 0; start + width <= hayWords.length; start += 1) {
      const window = hayWords.slice(start, start + width).join(' ');
      const score = similarity(needleN, window);
      if (score > best) {
        best = score;
        if (best >= 0.999) return best;
      }
    }
  }
  return best;
}

/** Fraction of the needle's significant words present in the haystack. */
export function tokenCoverage(needle, haystack) {
  const needleTokens = significantTokens(needle);
  if (!needleTokens.length) return 0;
  const hayWords = tokens(haystack);
  if (!hayWords.length) return 0;
  const hayJoined = hayWords.join(' ');
  const haySet = new Set(hayWords);
  let found = 0;
  for (const token of needleTokens) {
    if (haySet.has(token)) {
      found += 1;
    } else if (token.length > 3 && hayWords.some((w) => similarity(token, w) >= 0.85)) {
      found += 1;
    } else if (token.length > 5 && hayJoined.replace(/ /g, '').includes(token)) {
      // Handles decorative letter-spacing: "B R O O K" -> "brook".
      found += 1;
    }
  }
  return found / needleTokens.length;
}

export function fieldMatchScore(expected, ocrText) {
  return Math.max(bestWindowSimilarity(expected, ocrText),
                  tokenCoverage(expected, ocrText));
}

export function fixOcrDigits(value) {
  return String(value).replace(/[OoQDlI|iSsBZzG]/g, (c) => DIGIT_FIXES[c] || c);
}

function toNumber(raw) {
  let cleaned = fixOcrDigits(String(raw).trim());
  cleaned = cleaned.replace(/(?<=\d),(?=\d)/g, '.');
  cleaned = cleaned.replace(/[^\d.]/g, '');
  if (!cleaned || (cleaned.match(/\./g) || []).length > 1) return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

/* ---- Alcohol content --------------------------------------------------- */
const ALC_CONTEXT = /alc|abv|vol|alcohol|proof|grad/i;
const PERCENT_RE = /(?<![\d.])(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:%|percent|per cent)/gi;
const PERCENT_LOOSE_RE =
  /(?:alc(?:ohol)?\.?\s*(?:by\s*vol(?:ume)?)?|abv)\s*[:. ]?\s*(?<![\d.])(\d{1,2}(?:[.,]\d{1,2})?)\b/gi;
const PROOF_RE =
  /(?<![\d.])(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:°\s*)?proof|proof\s*[:. ]?\s*(?<![\d.])(\d{1,3}(?:[.,]\d{1,2})?)/gi;

export function parseAlcohol(text) {
  if (!text) return [];
  const results = [];
  const seen = new Set();

  const add = (kind, raw, source) => {
    const value = toNumber(raw);
    if (value === null) return;
    if (kind === 'abv' && !(value >= 0 && value <= 100)) return;
    if (kind === 'proof' && !(value >= 0 && value <= 200)) return;
    const key = `${kind}:${Math.round(value * 100) / 100}`;
    if (seen.has(key)) return;
    seen.add(key);
    results.push({
      kind,
      value,
      abv: kind === 'proof' ? value / 2 : value,
      source: String(source).trim(),
    });
  };

  for (const m of text.matchAll(PROOF_RE)) {
    const raw = m[1] || m[2];
    if (raw) add('proof', raw, m[0]);
  }
  for (const m of text.matchAll(PERCENT_RE)) {
    // Kept whether or not alcohol wording is nearby: some labels print only
    // "13.5%". ALC_CONTEXT is retained for readability of intent.
    void ALC_CONTEXT;
    add('abv', m[1], m[0]);
  }
  for (const m of text.matchAll(PERCENT_LOOSE_RE)) {
    add('abv', m[1], m[0]);
  }
  return results;
}

export function formatAlcohol(entry) {
  const trim = (n) => String(Number(n.toFixed(4)));
  if (entry.kind === 'proof') {
    return `${trim(entry.value)} proof (${trim(entry.abv)}% ABV)`;
  }
  return `${trim(entry.value)}% ABV`;
}

/* ---- Net contents ------------------------------------------------------ */
const UNIT_TO_ML = {
  ml: 1, milliliter: 1, millilitre: 1, milliliters: 1, millilitres: 1, cc: 1,
  l: 1000, liter: 1000, litre: 1000, liters: 1000, litres: 1000, lt: 1000,
  cl: 10, centiliter: 10, centilitre: 10,
  dl: 100,
  floz: ML_PER_FL_OZ, flozs: ML_PER_FL_OZ, fluidounce: ML_PER_FL_OZ,
  fluidounces: ML_PER_FL_OZ, oz: ML_PER_FL_OZ, ozs: ML_PER_FL_OZ,
  ounce: ML_PER_FL_OZ, ounces: ML_PER_FL_OZ,
  pt: ML_PER_PINT, pint: ML_PER_PINT, pints: ML_PER_PINT,
  qt: ML_PER_QUART, quart: ML_PER_QUART, quarts: ML_PER_QUART,
  gal: ML_PER_GALLON, gallon: ML_PER_GALLON, gallons: ML_PER_GALLON,
};

const QTY_RE = new RegExp(
  '(\\d{1,4}(?:[.,]\\d{1,3})?)\\s*'
  + '(fl\\.?\\s*oz|fluid\\s*ounces?|ounces?|oz|ml|milli ?lit(?:er|re)s?|'
  + 'cl|centilit(?:er|re)s?|dl|lit(?:er|re)s?|l|lt|pints?|pt|quarts?|qt|'
  + 'gallons?|gal|cc)\\b\\.?',
  'gi',
);

const BIG_UNITS = new Set(['pt', 'pint', 'pints', 'qt', 'quart', 'quarts',
                           'gal', 'gallon', 'gallons']);
const SMALL_UNITS = new Set(['floz', 'oz', 'ounce', 'ounces']);

function unitKey(raw) {
  return raw.toLowerCase().replace(/[^a-z]/g, '');
}

export function parseNetContents(text) {
  if (!text) return [];
  const raw = [];
  for (const m of text.matchAll(QTY_RE)) {
    const quantity = toNumber(m[1]);
    if (quantity === null || quantity <= 0) continue;
    const unit = unitKey(m[2]);
    const factor = UNIT_TO_ML[unit];
    if (factor === undefined) continue;
    raw.push({
      ml: quantity * factor,
      quantity,
      unit,
      source: m[0].trim(),
      start: m.index,
      end: m.index + m[0].length,
    });
  }

  // Merge compound imperial statements: "1 PT 9 FL OZ" is one quantity.
  const merged = [];
  let index = 0;
  while (index < raw.length) {
    const current = { ...raw[index] };
    let step = index + 1;
    while (step < raw.length
           && raw[step].start - current.end <= 2
           && BIG_UNITS.has(current.unit)
           && SMALL_UNITS.has(raw[step].unit)) {
      current.ml += raw[step].ml;
      current.source += ` ${raw[step].source}`;
      current.end = raw[step].end;
      step += 1;
    }
    merged.push(current);
    index = step;
  }

  return merged.map(({ start, end, ...rest }) => ({
    ...rest,
    ml: Math.round(rest.ml * 1000) / 1000,
  }));
}

export function formatMl(millilitres) {
  const trim = (n) => String(Number(n.toFixed(4)));
  if (millilitres >= 1000
      && Math.abs(millilitres / 1000 - Number((millilitres / 1000).toFixed(2))) < 1e-9) {
    return `${trim(millilitres / 1000)} L (${trim(millilitres)} mL)`;
  }
  return `${trim(millilitres)} mL`;
}

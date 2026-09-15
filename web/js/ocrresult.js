/**
 * The OCR result structure, and how several label panels combine.
 * Port of the data-handling half of labelcheck/ocr.py.
 */
export const LOW_CONFIDENCE = 45;

export function makeResult(overrides = {}) {
  return {
    text: '',
    words: [],
    imageWidth: 0,
    imageHeight: 0,
    mmPerPx: null,
    scaleSource: 'unknown',
    elapsed: 0,
    passes: [],
    truncated: false,
    ...overrides,
  };
}

/** Words grouped into text lines, in reading order. */
export function lines(result) {
  const grouped = new Map();
  for (const word of result.words) {
    const key = String(word.lineKey);
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(word);
  }
  const groups = [...grouped.values()];
  groups.sort((a, b) => {
    const at = Math.min(...a.map((w) => w.top));
    const bt = Math.min(...b.map((w) => w.top));
    if (at !== bt) return at - bt;
    return Math.min(...a.map((w) => w.left)) - Math.min(...b.map((w) => w.left));
  });
  return groups.map((g) => [...g].sort((x, y) => x.left - y.left));
}

export function lowConfidenceWords(result) {
  return result.words.filter((w) => w.conf < LOW_CONFIDENCE);
}

/** Words assembled into lines, without repeated lines. */
export function joinedText(words) {
  const fake = { words };
  const seen = new Set();
  const out = [];
  for (const line of lines(fake)) {
    const text = line.map((w) => w.text).join(' ');
    const fingerprint = text.split(/\s+/).join(' ').toLowerCase();
    if (fingerprint && seen.has(fingerprint)) continue;
    seen.add(fingerprint);
    out.push(text);
  }
  return out.join('\n');
}

/**
 * Combine several panels into one result for text comparison.
 *
 * Geometry deliberately does NOT survive: mmPerPx is cleared, because two
 * pictures can be taken at different scales and one conversion factor would
 * be wrong for at least one of them. Physical measurements must use a single
 * panel.
 */
export function mergeResults(results) {
  if (!results.length) return makeResult();
  if (results.length === 1) return results[0];

  const words = [];
  results.forEach((result, index) => {
    for (const word of result.words) {
      words.push({ ...word, lineKey: `p${index}:${word.lineKey}` });
    }
  });

  const passes = [];
  results.forEach((result, index) => {
    for (const name of result.passes) passes.push(`picture ${index + 1}: ${name}`);
  });

  return makeResult({
    text: results.map((r) => r.text).filter(Boolean).join('\n'),
    words,
    imageWidth: Math.max(...results.map((r) => r.imageWidth)),
    imageHeight: Math.max(...results.map((r) => r.imageHeight)),
    mmPerPx: null,
    scaleSource: 'varies by picture',
    elapsed: results.reduce((sum, r) => sum + r.elapsed, 0),
    passes,
    truncated: results.some((r) => r.truncated),
  });
}

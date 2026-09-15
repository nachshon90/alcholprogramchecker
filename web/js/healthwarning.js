/**
 * The Government Warning check - 27 CFR Part 16.
 * Port of labelcheck/healthwarning.py.
 *
 *   16.21  Exact statement. "GOVERNMENT WARNING" in capitals and bold.
 *   16.22  Minimum type size by container volume, and at most 12
 *          characters per inch.
 *
 * Type size is a physical measurement, so it is only checked when the
 * physical scale of the artwork is known. Otherwise this reports "cannot
 * check" - a false pass on a legibility rule is worse than an honest
 * unknown.
 */
import { finding, FAIL, PASS, UNKNOWN, WARN } from './findings.js';
import { lines as resultLines, mergeResults } from './ocrresult.js';
import { HEALTH_WARNING } from './rules.js';
import { bestWindowSimilarity, normalize } from './textnorm.js';

export const PREFIX = 'GOVERNMENT WARNING:';
export const PART_ONE = '(1) According to the Surgeon General, women should '
  + 'not drink alcoholic beverages during pregnancy because of the risk of '
  + 'birth defects.';
export const PART_TWO = '(2) Consumption of alcoholic beverages impairs your '
  + 'ability to drive a car or operate machinery, and may cause health '
  + 'problems.';
export const FULL_STATEMENT = `${PREFIX} ${PART_ONE} ${PART_TWO}`;

const SEGMENTS = [
  ['prefix', PREFIX, 'the words GOVERNMENT WARNING'],
  ['part_one', PART_ONE, 'part (1), the pregnancy warning'],
  ['part_two', PART_TWO, 'part (2), the driving and machinery warning'],
];

const SIZE_TIERS = [
  [237.0, 1.0, 'containers of 237 mL (8 fl oz) or less'],
  [3000.0, 2.0, 'containers over 237 mL and up to 3 L'],
  [Infinity, 3.0, 'containers over 3 L'],
];
export const MAX_CHARS_PER_INCH = 12.0;
const MM_PER_INCH = 25.4;

const WARNING_VOCAB = new Set(normalize(FULL_STATEMENT).split(' '));
const ANCHOR_WORDS = new Set(['government', 'warning', 'surgeon', 'pregnancy',
                              'machinery']);

export function requiredMm(volumeMl) {
  if (volumeMl === null || volumeMl === undefined || volumeMl <= 0) {
    return { mm: 2.0, description: SIZE_TIERS[1][2], assumed: true };
  }
  for (const [ceiling, minimum, description] of SIZE_TIERS) {
    if (volumeMl <= ceiling) return { mm: minimum, description, assumed: false };
  }
  return { mm: 3.0, description: SIZE_TIERS[2][2], assumed: false };
}

function lineIsWarning(words) {
  const texts = words.map((w) => normalize(w.text)).filter(Boolean);
  if (!texts.length) return false;
  if (texts.some((t) => ANCHOR_WORDS.has(t))) return true;
  if (texts.length < 3) return false;
  const hits = texts.filter((t) => WARNING_VOCAB.has(t)).length;
  return hits / texts.length >= 0.6;
}

export function locateWarning(result) {
  return resultLines(result).filter(lineIsWarning);
}

const letters = (s) => s.replace(/[^A-Za-z]/g, '');

/**
 * Measure capital-letter height from the words required to be capitals.
 * Mixed-case bounding boxes include descenders, which overstates type size;
 * GOVERNMENT and WARNING must be capitals, so they measure cleanly.
 */
function capHeightMm(warningLines, mmPerPx) {
  let candidates = [];
  for (const line of warningLines) {
    for (const word of line) {
      const stripped = letters(word.text).toUpperCase();
      if (stripped === 'GOVERNMENT' || stripped === 'WARNING') {
        candidates.push(word.height);
      }
    }
  }
  if (!candidates.length) {
    for (const line of warningLines) {
      for (const word of line) {
        const stripped = letters(word.text);
        if (stripped.length >= 3 && stripped === stripped.toUpperCase()) {
          candidates.push(word.height);
        }
      }
    }
  }
  if (!candidates.length) return null;
  candidates = candidates.sort((a, b) => a - b);
  return candidates[Math.floor(candidates.length / 2)] * mmPerPx;
}

function maxCharsPerInch(warningLines, mmPerPx) {
  const densities = [];
  for (const line of warningLines) {
    if (line.length < 3) continue;
    const left = Math.min(...line.map((w) => w.left));
    const right = Math.max(...line.map((w) => w.left + w.width));
    const widthPx = right - left;
    if (widthPx <= 0) continue;
    const characters = line.reduce((n, w) => n + w.text.length, 0) + (line.length - 1);
    const widthInches = (widthPx * mmPerPx) / MM_PER_INCH;
    if (widthInches <= 0) continue;
    densities.push(characters / widthInches);
  }
  return densities.length ? Math.max(...densities) : null;
}

/**
 * Fraction of dark pixels inside a set of word boxes, used only as a hint
 * about bold type. Needs a canvas; returns null when unavailable.
 */
function inkDensity(canvas, words) {
  if (!canvas || !words.length) return null;
  try {
    const context = canvas.getContext('2d', { willReadFrequently: true });
    let dark = 0;
    let total = 0;
    for (const word of words) {
      const x = Math.max(0, Math.round(word.left));
      const y = Math.max(0, Math.round(word.top));
      const w = Math.min(canvas.width - x, Math.round(word.width));
      const h = Math.min(canvas.height - y, Math.round(word.height));
      if (w <= 0 || h <= 0) continue;
      const { data } = context.getImageData(x, y, w, h);
      for (let i = 0; i < data.length; i += 4) {
        const luma = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
        total += 1;
        if (luma < 128) dark += 1;
      }
    }
    return total ? dark / total : null;
  } catch (error) {
    return null;
  }
}

export function check(result, volumeMl = null, canvas = null,
                     { requireFullCaps = true } = {}) {
  const findings = [];
  const warningLines = locateWarning(result);
  const warningWords = warningLines.flat();
  const foundText = warningLines
    .map((line) => line.map((w) => w.text).join(' ')).join('\n');

  // 1. Is it there at all?
  const overall = bestWindowSimilarity(FULL_STATEMENT, result.text);
  if (!warningLines.length && overall < 0.45) {
    findings.push(finding({
      field: HEALTH_WARNING,
      title: 'Government Health Warning is missing',
      status: FAIL,
      detail: 'The Government Health Warning could not be found anywhere on '
        + 'this label. Every alcoholic drink of 0.5% alcohol or more must '
        + 'carry it. If the warning is on another panel of the container, '
        + 'please check that panel as well.',
      expected: FULL_STATEMENT,
      found: '(nothing found)',
      cite: '27 CFR 16.21',
    }));
    return findings;
  }

  // 2. Is the wording right, segment by segment?
  const missing = [];
  for (const [, segmentText, plainName] of SEGMENTS) {
    if (bestWindowSimilarity(segmentText, result.text) < 0.72) missing.push(plainName);
  }
  if (missing.length) {
    findings.push(finding({
      field: HEALTH_WARNING,
      title: 'Government Health Warning wording is wrong or incomplete',
      status: FAIL,
      detail: 'This part of the warning is missing or does not match the '
        + `wording the law requires: ${missing.join('; ')}. The warning must `
        + 'be printed word for word.',
      expected: FULL_STATEMENT,
      found: foundText || '(not readable)',
      cite: '27 CFR 16.21',
    }));
  } else {
    findings.push(finding({
      field: HEALTH_WARNING,
      title: 'Government Health Warning wording is correct',
      status: PASS,
      detail: 'All three parts of the warning are present and match the '
        + 'required wording.',
      expected: FULL_STATEMENT,
      found: foundText,
      cite: '27 CFR 16.21',
    }));
  }

  // 3. "GOVERNMENT WARNING" must be in capital letters.
  const prefixWords = warningWords.filter((w) => {
    const s = letters(w.text).toUpperCase();
    return s === 'GOVERNMENT' || s === 'WARNING';
  });
  if (!prefixWords.length) {
    findings.push(finding({
      field: HEALTH_WARNING,
      title: 'Cannot check capital letters on GOVERNMENT WARNING',
      status: UNKNOWN,
      detail: 'The words GOVERNMENT WARNING could not be read clearly enough '
        + 'to confirm they are in capital letters. Please check this by eye.',
      cite: '27 CFR 16.21',
    }));
  } else {
    const lower = prefixWords
      .filter((w) => letters(w.text) !== letters(w.text).toUpperCase())
      .map((w) => w.text);
    if (lower.length) {
      findings.push(finding({
        field: HEALTH_WARNING,
        title: 'GOVERNMENT WARNING is not in capital letters',
        status: FAIL,
        detail: 'The words GOVERNMENT WARNING must be printed in capital '
          + `letters. On this label they read: ${lower.join(' ')}.`,
        expected: 'GOVERNMENT WARNING',
        found: prefixWords.map((w) => w.text).join(' '),
        cite: '27 CFR 16.21',
      }));
    } else {
      findings.push(finding({
        field: HEALTH_WARNING,
        title: 'GOVERNMENT WARNING is in capital letters',
        status: PASS,
        detail: 'The words GOVERNMENT WARNING are in capital letters, as required.',
        found: prefixWords.map((w) => w.text).join(' '),
        cite: '27 CFR 16.21',
      }));
    }
  }

  // 4. House-style check: the whole statement in capitals.
  if (requireFullCaps && warningWords.length) {
    const prefixSet = new Set(prefixWords);
    const body = warningWords.filter((w) => !prefixSet.has(w));
    const lowerBody = body
      .filter((w) => letters(w.text).length >= 3
                     && letters(w.text) !== letters(w.text).toUpperCase())
      .map((w) => w.text);
    if (lowerBody.length) {
      findings.push(finding({
        field: HEALTH_WARNING,
        title: 'Warning is not entirely in capital letters (house style)',
        status: WARN,
        advisory: true,
        detail: 'Your house style asks for the whole warning in capital '
          + 'letters. Some words here are in small letters, for example: '
          + `${lowerBody.slice(0, 6).join(', ')}. Note that federal law only `
          + 'requires the words GOVERNMENT WARNING to be in capitals, so this '
          + 'is a style preference, not a legal problem.',
        cite: 'House style (27 CFR 16.21 requires capitals only on GOVERNMENT WARNING)',
      }));
    } else {
      findings.push(finding({
        field: HEALTH_WARNING,
        title: 'Whole warning is in capital letters (house style)',
        status: PASS,
        advisory: true,
        detail: 'The entire warning is printed in capital letters.',
      }));
    }
  }

  // 5. Type size.
  const { mm: minimumMm, description: tier, assumed } = requiredMm(volumeMl);
  if (result.mmPerPx === null || result.mmPerPx === undefined) {
    findings.push(finding({
      field: HEALTH_WARNING,
      title: 'Cannot check how big the warning letters are',
      status: UNKNOWN,
      detail: 'To check letter height the tool needs to know the real-world '
        + "size of the label. Type the label's width in millimetres in the "
        + 'box on the check page. Without it, letter height cannot be '
        + `measured - this container needs letters at least ${minimumMm} mm tall.`,
      cite: '27 CFR 16.22',
    }));
  } else {
    const measured = capHeightMm(warningLines, result.mmPerPx);
    const assumption = assumed
      ? ' The container size was not given, so the tool assumed a normal bottle.'
      : '';
    if (measured === null) {
      findings.push(finding({
        field: HEALTH_WARNING,
        title: 'Cannot measure the warning letters',
        status: UNKNOWN,
        detail: 'The warning text could not be measured reliably. Please '
          + 'check letter height by eye: this container needs letters at '
          + `least ${minimumMm} mm tall.`,
        cite: '27 CFR 16.22',
      }));
    } else if (measured + 0.05 < minimumMm) {
      findings.push(finding({
        field: HEALTH_WARNING,
        title: 'Government Health Warning letters are too small',
        status: FAIL,
        detail: `The warning letters measure about ${measured.toFixed(2)} mm `
          + `tall. The law requires at least ${minimumMm} mm for ${tier}.${assumption}`,
        expected: `at least ${minimumMm} mm tall`,
        found: `about ${measured.toFixed(2)} mm tall`,
        cite: '27 CFR 16.22(a)',
      }));
    } else {
      findings.push(finding({
        field: HEALTH_WARNING,
        title: 'Government Health Warning letters are big enough',
        status: PASS,
        detail: `The warning letters measure about ${measured.toFixed(2)} mm `
          + `tall, meeting the ${minimumMm} mm minimum for ${tier}.${assumption}`,
        expected: `at least ${minimumMm} mm tall`,
        found: `about ${measured.toFixed(2)} mm tall`,
        cite: '27 CFR 16.22(a)',
      }));
    }

    // 6. No more than 12 characters per inch.
    const density = maxCharsPerInch(warningLines, result.mmPerPx);
    if (density !== null) {
      if (density > MAX_CHARS_PER_INCH + 0.5) {
        findings.push(finding({
          field: HEALTH_WARNING,
          title: 'Warning text is squeezed too tightly',
          status: FAIL,
          detail: `The warning is printed at about ${density.toFixed(1)} `
            + `characters per inch. The law allows no more than `
            + `${MAX_CHARS_PER_INCH}. The text needs more spacing.`,
          expected: `no more than ${MAX_CHARS_PER_INCH} characters per inch`,
          found: `about ${density.toFixed(1)} characters per inch`,
          cite: '27 CFR 16.22(b)',
        }));
      } else {
        findings.push(finding({
          field: HEALTH_WARNING,
          title: 'Warning text spacing is acceptable',
          status: PASS,
          detail: `The warning is printed at about ${density.toFixed(1)} `
            + `characters per inch, within the limit of ${MAX_CHARS_PER_INCH}.`,
          cite: '27 CFR 16.22(b)',
        }));
      }
    }
  }

  // 7. Bold type hint.
  if (canvas && prefixWords.length) {
    const prefixSet = new Set(prefixWords);
    const bodyWords = warningWords.filter((w) => !prefixSet.has(w));
    const prefixInk = inkDensity(canvas, prefixWords);
    const bodyInk = inkDensity(canvas, bodyWords);
    if (prefixInk !== null && bodyInk !== null && bodyInk > 0
        && prefixInk / bodyInk < 1.08) {
      findings.push(finding({
        field: HEALTH_WARNING,
        title: 'GOVERNMENT WARNING may not be in bold type',
        status: WARN,
        detail: 'The words GOVERNMENT WARNING must be in bold type. They do '
          + 'not look noticeably heavier than the rest of the warning, but '
          + 'this is hard to judge from an image. Please confirm by eye.',
        cite: '27 CFR 16.21',
      }));
    }
  }

  return findings;
}

/** Check the warning across every panel, measuring the one that carries it. */
export function checkPanels(scans, volumeMl = null, options = {}) {
  if (!scans.length) return { findings: [], panel: null };

  let bestIndex = null;
  let bestEvidence = 0;
  scans.forEach(({ result }, index) => {
    const evidence = locateWarning(result).reduce((n, line) => n + line.length, 0);
    if (evidence > bestEvidence) { bestEvidence = evidence; bestIndex = index; }
  });

  if (bestIndex === null) {
    const merged = mergeResults(scans.map((s) => s.result));
    return { findings: check(merged, volumeMl, null, options), panel: null };
  }
  const { result, canvas } = scans[bestIndex];
  return { findings: check(result, volumeMl, canvas, options), panel: bestIndex };
}

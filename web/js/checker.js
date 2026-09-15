/**
 * Orchestration: scanned panels in, one report out.
 * Port of labelcheck/checker.py.
 *
 * Deliberately pure: it takes OCR results that someone else produced, so it
 * can be tested in Node without a browser or an OCR engine.
 */
import { declaredMl, rulesFor } from './application.js';
import * as compare from './compare.js';
import { FAIL, PASS, SEVERITY_ORDER, STATUS_WORDS, UNKNOWN, WARN, worst } from './findings.js';
import { checkPanels } from './healthwarning.js';
import { lowConfidenceWords, mergeResults } from './ocrresult.js';
import { FIELD_LABELS, FIELD_ORDER } from './rules.js';
import { parseNetContents } from './textnorm.js';

export const TIME_BUDGET_SECONDS = 5.0;

export const VERDICT_TEXT = {
  [PASS]: 'PASS - everything matches',
  [FAIL]: 'PROBLEMS FOUND',
  [WARN]: 'CHECK A FEW THINGS BY HAND',
  [UNKNOWN]: 'COULD NOT CHECK EVERYTHING',
};

export function verdictText(report) {
  if (report.error) return 'COULD NOT CHECK';
  return VERDICT_TEXT[report.overall] || String(report.overall).toUpperCase();
}

export function statusWord(status) {
  return STATUS_WORDS[status] || String(status).toUpperCase();
}

export function warningPanelLabel(report) {
  if (report.warningPanel === null || report.panelCount < 2) return null;
  const name = report.imageNames[report.warningPanel] || '';
  const position = report.warningPanel === 0 ? 'front' : 'back';
  return `picture ${report.warningPanel + 1} (${position})`
    + (name ? ` - ${name}` : '');
}

/**
 * @param {Array} scans  [{ result, canvas, name }] - one per picture
 * @param {Object} app   declared product details
 */
export function checkLabel(scans, app, { requireFullCaps = true,
                                         elapsed = 0 } = {}) {
  const rules = rulesFor(app);
  const report = {
    reference: app.reference || '',
    imageNames: scans.map((s) => s.name || ''),
    beverageClass: rules.key,
    beverageDisplay: rules.displayName,
    beveragePlain: rules.plainName,
    authority: rules.authority,
    overall: UNKNOWN,
    fields: [],
    elapsed,
    ocrElapsed: 0,
    ocrPasses: [],
    scaleSource: 'unknown',
    ocrText: '',
    notes: [],
    error: null,
    warningPanel: null,
    get panelCount() { return Math.max(1, this.imageNames.length); },
  };

  if (!scans.length) {
    report.error = 'No label picture was supplied.';
    return report;
  }

  const results = scans.map((s) => s.result);
  const combined = mergeResults(results);
  report.ocrElapsed = combined.elapsed;
  report.ocrPasses = combined.passes;
  report.scaleSource = results.length === 1 ? results[0].scaleSource
                                            : combined.scaleSource;
  report.ocrText = combined.text;

  if (combined.truncated) {
    report.notes.push('Reading the pictures took longer than expected, so part '
      + 'of the check may be incomplete. Please look over the results carefully.');
  }
  if (!combined.text.trim()) {
    report.error = 'No text could be read from '
      + (results.length === 1 ? 'this image' : 'these images')
      + '. They may be blurry, very low resolution, or not labels. Try a '
      + 'sharper picture taken straight on.';
    return report;
  }

  if (lowConfidenceWords(combined).length
      > Math.max(8, combined.words.length * 0.35)) {
    report.notes.push('Much of the text was hard to read. A sharper or larger '
      + 'picture will give a more reliable result.');
  }

  // Volume drives the health-warning type-size tier: prefer the declared
  // figure, fall back to what the label itself states.
  let volumeMl = declaredMl(app);
  if (volumeMl === null) {
    const fromLabel = parseNetContents(combined.text);
    if (fromLabel.length) volumeMl = fromLabel[0].ml;
  }

  const grouped = new Map();
  const collect = (findings) => {
    for (const f of findings) {
      if (!grouped.has(f.field)) grouped.set(f.field, []);
      grouped.get(f.field).push(f);
    }
  };

  // Text fields see the pooled text of every panel.
  collect(compare.checkBrandName(app, combined, rules));
  collect(compare.checkClassType(app, combined, rules));
  collect(compare.checkAlcoholContent(app, combined, rules));
  collect(compare.checkNetContents(app, combined, rules));
  collect(compare.checkBottlerName(app, combined, rules));
  collect(compare.checkBottlerAddress(app, combined, rules));
  collect(compare.checkCountryOfOrigin(app, combined, rules));
  collect(compare.checkSulfites(app, combined, rules));

  // The warning is measured on whichever panel actually carries it.
  const { findings: warningFindings, panel } =
    checkPanels(scans, volumeMl, { requireFullCaps });
  report.warningPanel = panel;
  collect(warningFindings);

  for (const fieldKey of FIELD_ORDER) {
    const findings = grouped.get(fieldKey);
    if (!findings || !findings.length) continue;
    findings.sort((a, b) => SEVERITY_ORDER[a.status] - SEVERITY_ORDER[b.status]);
    report.fields.push({
      field: fieldKey,
      label: FIELD_LABELS[fieldKey],
      status: worst(findings),
      findings,
    });
  }

  // Advisory findings must never be the sole reason a label fails.
  const binding = allFindings(report).filter((f) => !f.advisory);
  report.overall = binding.length ? worst(binding) : UNKNOWN;
  return report;
}

export function allFindings(report) {
  return report.fields.flatMap((f) => f.findings);
}

export function counts(report) {
  const tally = { [PASS]: 0, [FAIL]: 0, [WARN]: 0, [UNKNOWN]: 0 };
  for (const f of allFindings(report)) tally[f.status] += 1;
  return tally;
}

export function problemFields(report) {
  return report.fields.filter((f) => [FAIL, UNKNOWN, WARN].includes(f.status));
}

export function matchedFields(report) {
  return report.fields.filter((f) => f.status === PASS);
}

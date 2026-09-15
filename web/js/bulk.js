/** The "check many labels" page. Everything runs in the browser. */
import { makeApplication } from './application.js';
import { allFindings, checkLabel, verdictText } from './checker.js';
import { normalizeHeader, parseCsv, toBool, toCsv } from './csv.js';
import { loadPicture, readLabel } from './ocr.js';
import { badge, esc, symbol } from './render.js';
import { FIELD_LABELS, FIELD_ORDER } from './rules.js';
import { STATUS_WORDS } from './findings.js';

const $ = (id) => document.getElementById(id);
const ALLOWED = /\.(png|jpe?g|tiff?|bmp|webp|gif)$/i;

const TEMPLATE = [
  ['image', 'image_2', 'reference', 'brand_name', 'class_type',
   'alcohol_content', 'net_contents', 'bottler_name', 'bottler_address',
   'country_of_origin', 'beverage_class', 'is_import', 'contains_sulfites',
   'label_width_mm', 'label_width_mm_2'],
  ['bourbon_front.png', 'bourbon_back.png', 'SKU-1001', 'Old Bridge',
   'Kentucky Straight Bourbon Whisky', '45% ABV', '750 mL',
   'Old Bridge Distillery', 'Frankfort, Kentucky', '', 'distilled_spirits',
   'no', '', '95', '95'],
];

function download(filename, text, type = 'text/csv') {
  const blob = new Blob(['﻿', text], { type: `${type};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$('template').addEventListener('click', () => {
  download('label-check-template.csv', toCsv(TEMPLATE));
});

function showError(message) {
  const box = $('error');
  box.querySelector('p').textContent = message;
  box.hidden = false;
}

function rowToApplication(record) {
  const values = {};
  for (const [header, raw] of Object.entries(record)) {
    const target = normalizeHeader(header);
    if (!target) continue;
    if (target === 'isImport') values.isImport = toBool(raw) === true;
    else if (target === 'containsSulfites') values.containsSulfites = toBool(raw);
    else if (target === 'labelWidthMm' || target === 'labelWidthMm2') {
      values[target] = Number(raw) > 0 ? Number(raw) : null;
    } else values[target] = raw;
  }
  return makeApplication(values);
}

/** Match a CSV file name to a chosen file, ignoring any folder prefix. */
function findPicture(files, named) {
  if (!named) return null;
  const wanted = named.replace(/\\/g, '/').split('/').pop().toLowerCase();
  return files.get(wanted) || null;
}

$('bulk-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('error').hidden = true;

  const csvFile = $('csvFile').files[0];
  const pictures = [...$('imageFiles').files];
  if (!csvFile) { showError('Please choose the CSV file listing your labels.'); return; }
  if (!pictures.length) { showError('Please choose the label pictures.'); return; }

  const byName = new Map();
  for (const file of pictures) byName.set(file.name.toLowerCase(), file);

  let parsed;
  try {
    parsed = parseCsv(await csvFile.text());
  } catch (error) {
    showError(`That CSV file could not be read: ${error.message}`);
    return;
  }
  if (!parsed.rows.length) {
    showError('That CSV file has a header but no data rows.');
    return;
  }
  if (!parsed.headers.some((h) => normalizeHeader(h) === 'imagePath')) {
    showError('The CSV needs a column naming each label image file. Name it '
      + "'image' (other accepted names: file, filename, label, artwork).");
    return;
  }

  $('setup').hidden = true;
  $('progress').hidden = false;

  const started = performance.now();
  const reports = [];

  for (const [index, record] of parsed.rows.entries()) {
    const app = rowToApplication(record);
    if (!app.reference) app.reference = `row ${index + 2}`;
    $('progress-detail').textContent =
      `Label ${index + 1} of ${parsed.rows.length}: ${app.reference}`;
    $('progress-bar').style.width = `${Math.round((index / parsed.rows.length) * 100)}%`;

    const entries = [[app.imagePath, app.labelWidthMm],
                     [app.imagePath2, app.labelWidthMm2]]
      .filter(([path]) => path && path.trim());

    const scans = [];
    const problems = [];
    for (const [named, widthMm] of entries) {
      if (!ALLOWED.test(named)) {
        problems.push(`'${named}' is not an image type the tool accepts.`);
        continue;
      }
      const file = findPicture(byName, named);
      if (!file) {
        problems.push(`'${named}' was not among the pictures you chose.`);
        continue;
      }
      try {
        const { source, dpi } = await loadPicture(file);
        const result = await readLabel(source, { labelWidthMm: widthMm, dpi });
        const canvas = document.createElement('canvas');
        canvas.width = source.width;
        canvas.height = source.height;
        canvas.getContext('2d', { willReadFrequently: true }).drawImage(source, 0, 0);
        scans.push({ result, canvas, name: file.name });
      } catch (error) {
        problems.push(`'${named}' could not be read: ${error.message}`);
      }
    }

    if (!scans.length) {
      reports.push({
        reference: app.reference,
        imageNames: [app.imagePath],
        beveragePlain: 'unknown',
        beverageDisplay: 'unknown',
        overall: 'unknown',
        fields: [],
        elapsed: 0,
        notes: [],
        error: problems.join(' ') || 'No label picture could be read for this row.',
        warningPanel: null,
        panelCount: 1,
      });
      continue;
    }

    const report = checkLabel(scans, app, { elapsed: 0 });
    for (const problem of problems) report.notes.push(problem);
    reports.push(report);
  }

  const elapsed = (performance.now() - started) / 1000;
  $('progress').hidden = true;
  renderBatch(reports, elapsed);
});

function renderBatch(reports, elapsed) {
  const tally = { pass: 0, fail: 0, warn: 0, unknown: 0 };
  for (const report of reports) {
    tally[report.error ? 'unknown' : report.overall] += 1;
  }

  let html = `
    <h2>Results for ${reports.length} label${reports.length === 1 ? '' : 's'}</h2>
    <div class="tiles">
      <div class="tile t-pass"><span class="n">${tally.pass}</span>
        <span class="k">passed</span></div>
      <div class="tile t-fail"><span class="n">${tally.fail}</span>
        <span class="k">had problems</span></div>
      <div class="tile t-warn"><span class="n">${tally.warn + tally.unknown}</span>
        <span class="k">need a human look</span></div>
    </div>
    <p class="lead">Checked in ${elapsed.toFixed(1)} seconds &ndash; an average
      of ${(elapsed / Math.max(1, reports.length)).toFixed(1)} seconds each.</p>
    <div class="actions">
      <button type="button" id="download">Download all results as a spreadsheet</button>
      <a class="button secondary" href="bulk.html">Check another batch</a>
    </div>
    <h3>Every label</h3>
    <table class="results">
      <thead><tr>
        <th scope="col">Reference</th><th scope="col">Picture</th>
        <th scope="col">Kind of drink</th><th scope="col">Result</th>
        <th scope="col">What to look at</th>
      </tr></thead><tbody>`;

  for (const report of reports) {
    const status = report.error ? 'unknown' : report.overall;
    const issues = report.error ? [] : allFindings(report).filter((f) => f.status !== 'pass');
    const detail = report.error
      ? esc(report.error)
      : (issues.length
        ? `<ul style="margin:0; padding-left:1.2rem">${issues.map((f) =>
            `<li>${symbol(f.status)} ${esc(f.title)}${f.advisory
              ? ' <span class="tag-advisory">ADVICE ONLY</span>' : ''}</li>`).join('')}</ul>`
        : 'Everything matched.');
    html += `<tr class="r-${status}">
      <td>${esc(report.reference) || '&mdash;'}</td>
      <td>${esc((report.imageNames || []).join(', '))}</td>
      <td>${esc(report.beveragePlain)}</td>
      <td>${badge(status, report.error ? 'COULD NOT CHECK' : verdictText(report))}</td>
      <td>${detail}</td></tr>`;
  }
  html += '</tbody></table>';

  $('results').innerHTML = html;
  $('results').hidden = false;
  $('download').addEventListener('click', () => download(
    'label-check-results.csv', resultsCsv(reports)));
}

function resultsCsv(reports) {
  const header = ['reference', 'image', 'image_2', 'pictures_checked',
    'beverage_type', 'overall_result', 'seconds',
    ...FIELD_ORDER.map((k) => FIELD_LABELS[k]), 'problems', 'notes'];
  const rows = [header];

  for (const report of reports) {
    const byField = new Map((report.fields || []).map((f) => [f.field, f]));
    const names = report.imageNames || [];
    const problems = report.error || (report.fields ? allFindings(report)
      .filter((f) => f.status !== 'pass').map((f) => f.title).join('; ') : '');
    rows.push([
      report.reference, names[0] || '', names[1] || '', names.length || 1,
      report.beverageDisplay,
      report.error ? 'COULD NOT CHECK' : verdictText(report),
      (report.elapsed || 0).toFixed(2),
      ...FIELD_ORDER.map((key) => {
        const field = byField.get(key);
        return field ? (STATUS_WORDS[field.status] || field.status) : 'not checked';
      }),
      problems, (report.notes || []).join(' '),
    ]);
  }
  return toCsv(rows);
}

/** Rendering helpers shared by the check and batch pages. */
import {
  allFindings, counts, matchedFields, problemFields, statusWord, verdictText,
  warningPanelLabel,
} from './checker.js';

export function esc(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// Status is shown as a symbol AND a word as well as a colour, so results
// stay readable without colour vision.
const SYMBOLS = { pass: '&#10004;', fail: '&#10006;', warn: '!', unknown: '?' };
export const symbol = (status) => SYMBOLS[status] || '?';

export function badge(status, word) {
  return `<span class="badge b-${esc(status)}">${symbol(status)} ${esc(word)}</span>`;
}

function findingBlock(finding) {
  const advisory = finding.advisory
    ? ' <span class="tag-advisory">ADVICE ONLY</span>' : '';
  const compare = (finding.expected || finding.found) ? `
    <dl class="compare">
      ${finding.expected ? `<dt>Should be:</dt><dd>${esc(finding.expected)}</dd>` : ''}
      ${finding.found ? `<dt>On the label:</dt><dd>${esc(finding.found)}</dd>` : ''}
    </dl>` : '';
  const cite = finding.cite ? `<p class="cite">Rule: ${esc(finding.cite)}</p>` : '';
  return `
    <div class="finding">
      <p class="title">${symbol(finding.status)} ${esc(finding.title)}${advisory}</p>
      <p>${esc(finding.detail)}</p>
      ${compare}${cite}
    </div>`;
}

export function renderReport(report, thumbnails = []) {
  const verdict = report.error ? 'unknown' : report.overall;
  const panels = report.panelCount > 1
    ? `Checked ${report.panelCount} pictures together as one container.` : '';

  let html = `
    <h2>Result${report.reference ? ` for ${esc(report.reference)}` : ''}</h2>
    <div class="verdict v-${esc(verdict)}">
      <div class="mark" aria-hidden="true">${symbol(verdict)}</div>
      <div>
        <div class="text">${esc(verdictText(report))}</div>
        <div class="sub">
          Checked as: <strong>${esc(report.beveragePlain)}</strong>
          (${esc(report.beverageDisplay)}, ${esc(report.authority)}).
          ${esc(panels)}
          Took ${report.elapsed.toFixed(1)} seconds.
        </div>
      </div>
    </div>`;

  if (report.error) {
    html += `<div class="notice error"><p>${esc(report.error)}</p></div>`;
  }
  for (const note of report.notes) {
    html += `<div class="notice warn"><p>${esc(note)}</p></div>`;
  }

  const panelLabel = warningPanelLabel(report);
  if (panelLabel) {
    html += `<div class="notice"><p>The Government Health Warning was found on
      <strong>${esc(panelLabel)}</strong>, and its letter size was measured on
      that picture.</p></div>`;
  }

  if (!report.error) {
    const tally = counts(report);
    html += `
      <div class="tiles">
        <div class="tile t-pass"><span class="n">${tally.pass}</span>
          <span class="k">things that match</span></div>
        <div class="tile t-fail"><span class="n">${tally.fail}</span>
          <span class="k">problems found</span></div>
        <div class="tile t-warn"><span class="n">${tally.warn + tally.unknown}</span>
          <span class="k">to check by hand</span></div>
      </div>`;

    const problems = problemFields(report);
    if (problems.length) {
      html += '<h3>What you need to look at</h3><p>These are listed worst first.</p>';
      for (const field of problems) {
        html += `
          <div class="result-row s-${esc(field.status)}">
            <div class="result-head">
              <span class="name">${esc(field.label)}</span>
              ${badge(field.status, statusWord(field.status))}
            </div>
            ${field.findings.map(findingBlock).join('')}
          </div>`;
      }
    }

    const good = matchedFields(report);
    if (good.length) {
      html += '<h3>What matched correctly</h3>';
      for (const field of good) {
        html += `
          <div class="result-row s-${esc(field.status)}">
            <div class="result-head">
              <span class="name">${esc(field.label)}</span>
              ${badge(field.status, statusWord(field.status))}
            </div>
            ${field.findings.map((f) =>
              `<p>${symbol(f.status)} ${esc(f.detail)}</p>`).join('')}
          </div>`;
      }
    }
  }

  const shown = thumbnails.filter(Boolean);
  if (shown.length) {
    html += `<h3>The picture${shown.length === 1 ? '' : 's'} you sent</h3>
      <div class="preview-row">`;
    thumbnails.forEach((url, index) => {
      if (!url) return;
      const side = thumbnails.length > 1
        ? ` &ndash; ${index === 0 ? 'front' : 'back'}` : '';
      const name = report.imageNames[index]
        ? `<br><span class="small muted">${esc(report.imageNames[index])}</span>` : '';
      html += `<figure class="label-preview">
        <img src="${esc(url)}" alt="A small copy of label picture ${index + 1}">
        <figcaption>Picture ${index + 1}${side}${name}</figcaption>
      </figure>`;
    });
    html += '</div>';
  }

  if (report.ocrText) {
    const scale = report.scaleSource && report.scaleSource !== 'unknown'
      ? ` Real-world size taken from: ${esc(report.scaleSource)}.` : '';
    html += `
      <details>
        <summary>Show the words the computer read from your label</summary>
        <p class="small">If something below looks wrong, the picture may be
          blurry or at an angle. A clearer picture usually fixes it.${scale}</p>
        <pre class="ocr">${esc(report.ocrText)}</pre>
      </details>`;
  }

  return html;
}

export { allFindings, counts, statusWord, verdictText };

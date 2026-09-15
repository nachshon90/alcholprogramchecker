/** The "check one label" page. */
import { makeApplication } from './application.js';
import { checkLabel } from './checker.js';
import { loadPicture, readLabel } from './ocr.js';
import { renderReport } from './render.js';
import { classChoices } from './rules.js';

const $ = (id) => document.getElementById(id);
const ALLOWED = /\.(png|jpe?g|tiff?|bmp|webp|gif)$/i;
const MAX_BYTES = 25 * 1024 * 1024;

// Populate the beverage list from the rules, so the two cannot drift apart.
for (const [key, name] of classChoices()) {
  const option = document.createElement('option');
  option.value = key;
  option.textContent = name;
  $('beverageClass').append(option);
}

function showError(message) {
  const box = $('error');
  box.querySelector('p').textContent = message;
  box.hidden = false;
  box.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function clearError() { $('error').hidden = true; }

function setProgress(text, fraction) {
  $('progress-detail').textContent = text;
  $('progress-bar').style.width = `${Math.round((fraction || 0) * 100)}%`;
}

async function thumbnail(source, maxSize = 480) {
  const scale = Math.min(1, maxSize / Math.max(source.width, source.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(source.width * scale));
  canvas.height = Math.max(1, Math.round(source.height * scale));
  canvas.getContext('2d').drawImage(source, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.72);
}

function readForm() {
  const sulfites = $('containsSulfites').value;
  return makeApplication({
    brandName: $('brandName').value.trim(),
    classType: $('classType').value.trim(),
    alcoholContent: $('alcoholContent').value.trim(),
    netContents: $('netContents').value.trim(),
    bottlerName: $('bottlerName').value.trim(),
    bottlerAddress: $('bottlerAddress').value.trim(),
    countryOfOrigin: $('countryOfOrigin').value.trim(),
    beverageClass: $('beverageClass').value,
    isImport: $('isImport').checked,
    containsSulfites: sulfites === 'yes' ? true : (sulfites === 'no' ? false : null),
    labelWidthMm: Number($('width1').value) || null,
    labelWidthMm2: Number($('width2').value) || null,
    reference: $('reference').value.trim(),
  });
}

function chosenPictures() {
  const app = readForm();
  const widths = [app.labelWidthMm, app.labelWidthMm2];
  const files = [$('image1').files[0], $('image2').files[0]];
  const picked = [];
  files.forEach((file, index) => {
    if (!file) return;
    if (!ALLOWED.test(file.name)) {
      throw new Error(`Picture ${index + 1} is not a file type the tool `
        + 'accepts. Please use a PNG, JPEG, TIFF, BMP, WEBP or GIF picture.');
    }
    if (file.size > MAX_BYTES) {
      throw new Error(`Picture ${index + 1} is larger than the 25 MB limit.`);
    }
    if (file.size === 0) {
      throw new Error(`Picture ${index + 1} appears to be empty.`);
    }
    picked.push({ file, widthMm: widths[index], position: index });
  });
  return { app, picked };
}

$('check-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  clearError();

  let app;
  let picked;
  try {
    ({ app, picked } = chosenPictures());
  } catch (error) {
    showError(error.message);
    return;
  }
  if (!picked.length) {
    showError('Please choose a picture of the label to check.');
    return;
  }

  $('setup').hidden = true;
  $('results').hidden = true;
  $('again').hidden = true;
  $('progress').hidden = false;
  setProgress('Starting the text reader', 0.02);

  const started = performance.now();
  try {
    const scans = [];
    const thumbnails = [];

    for (const [index, entry] of picked.entries()) {
      const { source, dpi } = await loadPicture(entry.file);
      thumbnails.push(await thumbnail(source));
      const label = picked.length > 1 ? `picture ${index + 1}` : 'the label';
      const result = await readLabel(source, {
        labelWidthMm: entry.widthMm,
        dpi,
        onProgress: (message) => {
          const base = index / picked.length;
          const share = (message.progress || 0) / picked.length;
          const what = message.status === 'recognizing text'
            ? `Reading ${label}` : `Loading the text reader (${message.status})`;
          setProgress(what, Math.min(0.98, base + share));
        },
      });
      // The prepared canvas is not retained; bold detection uses the
      // original picture drawn at its own size.
      const canvas = document.createElement('canvas');
      canvas.width = source.width;
      canvas.height = source.height;
      canvas.getContext('2d', { willReadFrequently: true })
        .drawImage(source, 0, 0);
      scans.push({ result, canvas, name: entry.file.name });
    }

    setProgress('Comparing with your details', 0.99);
    const elapsed = (performance.now() - started) / 1000;
    const report = checkLabel(scans, app, { elapsed });

    $('progress').hidden = true;
    $('results').innerHTML = renderReport(report, thumbnails);
    $('results').hidden = false;
    $('again').hidden = false;
    $('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    $('progress').hidden = true;
    $('setup').hidden = false;
    showError(`Something went wrong while checking: ${error.message}`);
  }
});

$('again-button').addEventListener('click', () => {
  $('results').hidden = true;
  $('again').hidden = true;
  $('setup').hidden = false;
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

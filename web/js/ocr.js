/**
 * On-device OCR in the browser, using the vendored Tesseract WebAssembly
 * build. Port of the engine half of labelcheck/ocr.py.
 *
 * Nothing leaves the browser. Every file this loads is served from this same
 * site, so checking a label makes no network request at all.
 */
import { joinedText, makeResult } from './ocrresult.js';

const WORKER_PATH = 'vendor/tesseract/worker.min.js';
const CORE_PATH = 'vendor/core';
const LANG_PATH = 'vendor/lang';

export const MAX_OCR_DIMENSION = 2000;
export const MIN_OCR_DIMENSION = 1000;
const MM_PER_INCH = 25.4;

let workerPromise = null;

/** Start the OCR engine once and reuse it; loading the model is the slow part. */
export function getWorker(onProgress) {
  if (!workerPromise) {
    workerPromise = Tesseract.createWorker('eng', 1, {
      workerPath: WORKER_PATH,
      corePath: CORE_PATH,
      langPath: LANG_PATH,
      gzip: true,
      logger: (message) => {
        if (onProgress && message.status) onProgress(message);
      },
    }).catch((error) => {
      workerPromise = null;   // let a later attempt retry
      throw error;
    });
  }
  return workerPromise;
}

/* ---- Physical scale ---------------------------------------------------- */

/**
 * Read pixel density from the file's own bytes.
 *
 * Browsers do not expose image DPI, so the PNG `pHYs` chunk and the JPEG
 * JFIF density fields are read directly. This is what lets scanned artwork
 * be measured without the operator reaching for a ruler.
 */
export function readDpi(buffer) {
  const bytes = new Uint8Array(buffer);
  // PNG: 89 50 4E 47
  if (bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) {
    const view = new DataView(buffer);
    let offset = 8;
    while (offset + 8 < bytes.length) {
      const length = view.getUint32(offset);
      const type = String.fromCharCode(bytes[offset + 4], bytes[offset + 5],
                                       bytes[offset + 6], bytes[offset + 7]);
      if (type === 'pHYs') {
        const perUnitX = view.getUint32(offset + 8);
        const unit = bytes[offset + 16];
        if (unit === 1 && perUnitX > 0) return (perUnitX * 0.0254); // px/m -> DPI
        return null;
      }
      if (type === 'IDAT' || type === 'IEND') return null;
      offset += 12 + length;
    }
    return null;
  }
  // JPEG: FF D8, then an APP0 JFIF segment carrying density units.
  if (bytes[0] === 0xff && bytes[1] === 0xd8) {
    const view = new DataView(buffer);
    let offset = 2;
    while (offset + 4 < bytes.length) {
      if (bytes[offset] !== 0xff) break;
      const marker = bytes[offset + 1];
      const length = view.getUint16(offset + 2);
      if (marker === 0xe0 && length >= 14) {
        const units = bytes[offset + 11];
        const densityX = view.getUint16(offset + 12);
        if (densityX > 0) {
          if (units === 1) return densityX;             // dots per inch
          if (units === 2) return densityX * 2.54;      // dots per cm
        }
        return null;
      }
      if (marker === 0xda) break;                        // start of scan
      offset += 2 + length;
    }
  }
  return null;
}

function physicalScale(width, labelWidthMm, dpi) {
  if (labelWidthMm && labelWidthMm > 0) {
    return { mmPerPx: labelWidthMm / width, scaleSource: 'measured label width' };
  }
  // 72 is what software writes when it has nothing better to record.
  if (dpi && dpi >= 96) {
    return {
      mmPerPx: MM_PER_INCH / dpi,
      scaleSource: `image metadata (${Math.round(dpi)} DPI)`,
    };
  }
  return { mmPerPx: null, scaleSource: 'unknown' };
}

/* ---- Preprocessing ----------------------------------------------------- */

/** Grayscale, contrast-stretch and rescale. Returns { canvas, scale }. */
export function prepare(source) {
  const longest = Math.max(source.width, source.height);
  let scale = 1;
  if (longest > MAX_OCR_DIMENSION) scale = MAX_OCR_DIMENSION / longest;
  else if (longest < MIN_OCR_DIMENSION) {
    // Upscaling small artwork measurably improves recall on small print.
    scale = Math.min(MIN_OCR_DIMENSION / longest, 3);
  }

  const width = Math.max(1, Math.round(source.width * scale));
  const height = Math.max(1, Math.round(source.height * scale));
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  context.imageSmoothingQuality = 'high';
  context.drawImage(source, 0, 0, width, height);

  const image = context.getImageData(0, 0, width, height);
  const { data } = image;
  const histogram = new Uint32Array(256);
  for (let i = 0; i < data.length; i += 4) {
    const luma = (0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]) | 0;
    data[i] = luma; data[i + 1] = luma; data[i + 2] = luma;
    histogram[luma] += 1;
  }

  // Autocontrast with a 1% cutoff at each end, matching ImageOps.autocontrast.
  const pixels = width * height;
  const cutoff = Math.floor(pixels * 0.01);
  let low = 0; let high = 255; let seen = 0;
  for (let v = 0; v < 256; v += 1) { seen += histogram[v]; if (seen > cutoff) { low = v; break; } }
  seen = 0;
  for (let v = 255; v >= 0; v -= 1) { seen += histogram[v]; if (seen > cutoff) { high = v; break; } }
  if (high > low) {
    const range = high - low;
    const lookup = new Uint8Array(256);
    for (let v = 0; v < 256; v += 1) {
      lookup[v] = Math.max(0, Math.min(255, Math.round(((v - low) * 255) / range)));
    }
    for (let i = 0; i < data.length; i += 4) {
      const value = lookup[data[i]];
      data[i] = value; data[i + 1] = value; data[i + 2] = value;
    }
  }
  context.putImageData(image, 0, 0);
  return { canvas, scale };
}

/* ---- Recognition ------------------------------------------------------- */

/**
 * Flatten tesseract.js output into words, tagging each with the line it came
 * from. The word objects themselves carry no line number, so the line
 * identity has to be captured while walking blocks -> paragraphs -> lines.
 * Without it every word lands on its own line and the Government Warning
 * can never be measured.
 */
function wordsFrom(data) {
  const words = [];
  let lineId = 0;
  for (const block of data.blocks || []) {
    for (const paragraph of block.paragraphs || []) {
      for (const line of paragraph.lines || []) {
        for (const word of line.words || []) words.push({ word, lineId });
        lineId += 1;
      }
    }
  }
  if (!words.length && Array.isArray(data.words)) {
    data.words.forEach((word, index) => {
      words.push({ word, lineId: word.line_num ?? index });
    });
  }
  return words;
}

function toWords(entries, scale, passId, topOffset = 0) {
  const inverse = scale ? 1 / scale : 1;
  const out = [];
  for (const { word, lineId } of entries) {
    const text = (word.text || '').trim();
    if (!text) continue;
    const confidence = typeof word.confidence === 'number' ? word.confidence : -1;
    if (confidence < 0) continue;
    const box = word.bbox || {};
    const top = (box.y0 || 0) + topOffset;
    out.push({
      text,
      conf: confidence,
      left: Math.round((box.x0 || 0) * inverse),
      top: Math.round(top * inverse),
      width: Math.round(((box.x1 || 0) - (box.x0 || 0)) * inverse),
      height: Math.round(((box.y1 || 0) - (box.y0 || 0)) * inverse),
      // Namespaced per pass so lines from different passes never merge.
      lineKey: `${passId}-${lineId}`,
    });
  }
  return out;
}

async function runPass(worker, canvas, psm) {
  await worker.setParameters({ tessedit_pageseg_mode: String(psm) });
  const { data } = await worker.recognize(canvas, {}, { blocks: true, text: true });
  return wordsFrom(data);
}

function bandCanvas(canvas, top, bottom) {
  const band = document.createElement('canvas');
  band.width = canvas.width;
  band.height = bottom - top;
  band.getContext('2d').drawImage(canvas, 0, top, canvas.width, bottom - top,
                                  0, 0, canvas.width, bottom - top);
  return band;
}

/**
 * Read one label picture.
 *
 * A sparse-text pass handles display type. A banded pass then recovers small
 * mandatory print that a very large brand name hides: Tesseract sizes its
 * noise filter against the dominant text on the page, so the alcohol content
 * and net contents can vanish entirely even though they are perfectly
 * legible in isolation. A final block-text pass runs only if the health
 * warning has still not been found.
 */
export async function readLabel(source, { labelWidthMm = null, dpi = null,
                                          onProgress = null } = {}) {
  const started = performance.now();
  const worker = await getWorker(onProgress);
  const { canvas, scale } = prepare(source);

  const words = [];
  const passes = [];

  words.push(...toWords(await runPass(worker, canvas, 11), scale, 'a'));
  passes.push('sparse text (psm 11)');

  // Banded pass: two overlapping horizontal halves.
  const bands = 2;
  const step = Math.max(1, Math.floor(canvas.height / bands));
  const margin = Math.floor(step * 0.15);
  for (let index = 0; index < bands; index += 1) {
    const top = Math.max(0, index * step - margin);
    const bottom = Math.min(canvas.height, (index + 1) * step + margin);
    if (bottom - top < 20) continue;
    const band = bandCanvas(canvas, top, bottom);
    words.push(...toWords(await runPass(worker, band, 11), scale, `b${index}`, top));
  }
  passes.push('banded sparse text');

  const soFar = joinedText(words).toLowerCase();
  let truncated = false;
  if (!soFar.includes('government') || !soFar.includes('surgeon')) {
    try {
      words.push(...toWords(await runPass(worker, canvas, 6), scale, 'c'));
      passes.push('block text (psm 6)');
    } catch (error) {
      truncated = true;
    }
  }

  const { mmPerPx, scaleSource } = physicalScale(source.width, labelWidthMm, dpi);
  return makeResult({
    text: joinedText(words),
    words,
    imageWidth: source.width,
    imageHeight: source.height,
    mmPerPx,
    scaleSource,
    elapsed: (performance.now() - started) / 1000,
    passes,
    truncated,
  });
}

/** Decode a File into something drawable, plus its DPI. */
export async function loadPicture(file) {
  const buffer = await file.arrayBuffer();
  const dpi = readDpi(buffer);
  const blob = new Blob([buffer], { type: file.type || 'image/png' });
  let source;
  if (typeof createImageBitmap === 'function') {
    source = await createImageBitmap(blob);
  } else {
    source = await new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error('That file could not be read as an image.'));
      image.src = URL.createObjectURL(blob);
    });
  }
  return { source, dpi, blob };
}

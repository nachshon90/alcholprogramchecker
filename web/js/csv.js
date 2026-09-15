/** Minimal CSV reading and writing, with spreadsheet-injection guards. */

/** Parse CSV text into an array of row objects keyed by header name. */
export function parseCsv(text) {
  const clean = text.replace(/^﻿/, '');   // Excel writes a byte order mark
  const rows = [];
  let row = [];
  let value = '';
  let quoted = false;

  for (let i = 0; i < clean.length; i += 1) {
    const ch = clean[i];
    if (quoted) {
      if (ch === '"') {
        if (clean[i + 1] === '"') { value += '"'; i += 1; } else { quoted = false; }
      } else { value += ch; }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ',') {
      row.push(value); value = '';
    } else if (ch === '\n') {
      row.push(value); rows.push(row); row = []; value = '';
    } else if (ch !== '\r') {
      value += ch;
    }
  }
  if (value !== '' || row.length) { row.push(value); rows.push(row); }

  const nonEmpty = rows.filter((r) => r.some((cell) => cell.trim() !== ''));
  if (!nonEmpty.length) return { headers: [], rows: [] };
  const headers = nonEmpty[0].map((h) => h.trim());
  const out = nonEmpty.slice(1).map((cells) => {
    const record = {};
    headers.forEach((header, index) => { record[header] = (cells[index] || '').trim(); });
    return record;
  });
  return { headers, rows: out };
}

// Characters that make a spreadsheet treat a cell as a formula. Values here
// come from OCR of an uploaded image, so a crafted label could otherwise
// execute when the results are opened in Excel.
const INJECTION = ['=', '+', '-', '@', '\t', '\r'];

export function csvSafe(value) {
  let text = value === null || value === undefined ? '' : String(value);
  text = text.replace(/\r\n|\n|\r/g, ' ');
  if (INJECTION.some((c) => text.startsWith(c))) text = `'${text}`;
  return text;
}

export function toCsv(rows) {
  return rows.map((row) => row.map((cell) => {
    const safe = csvSafe(cell);
    return /[",]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
  }).join(',')).join('\r\n');
}

/** Accepted column spellings, mirroring labelcheck/application.py. */
const ALIASES = {
  imagePath: ['image', 'image_path', 'file', 'filename', 'file_name', 'label',
    'label_image', 'artwork', 'image_file', 'front_image', 'image_1', 'image1',
    'front', 'front_label'],
  imagePath2: ['image_2', 'image2', 'image_path_2', 'back_image', 'image_back',
    'second_image', 'back', 'back_label', 'back_label_image', 'file_2', 'file2',
    'rear_image'],
  brandName: ['brand', 'brand_name', 'brandname'],
  classType: ['class', 'type', 'class_type', 'classtype', 'class/type',
    'class_or_type', 'fanciful_name', 'product_class'],
  alcoholContent: ['abv', 'alcohol', 'alcohol_content', 'alc',
    'alcohol_by_volume', 'proof', 'alc_content'],
  netContents: ['net_contents', 'net', 'volume', 'size', 'netcontents',
    'container_size', 'fill'],
  bottlerName: ['bottler', 'bottler_name', 'producer', 'producer_name',
    'bottled_by', 'importer', 'importer_name', 'company', 'company_name',
    'name_and_address'],
  bottlerAddress: ['address', 'bottler_address', 'producer_address',
    'city_state', 'city_and_state'],
  countryOfOrigin: ['country', 'country_of_origin', 'origin'],
  beverageClass: ['beverage_class', 'beverage_type', 'commodity',
    'product_type', 'beverage', 'category'],
  isImport: ['is_import', 'import', 'imported', 'is_imported'],
  containsSulfites: ['contains_sulfites', 'sulfites', 'sulphites', 'sulfite'],
  labelWidthMm: ['label_width_mm', 'label_width', 'width_mm',
    'physical_width_mm', 'front_label_width_mm', 'label_width_mm_1'],
  labelWidthMm2: ['label_width_mm_2', 'label_width_2', 'width_mm_2',
    'back_label_width_mm', 'second_label_width_mm'],
  reference: ['reference', 'ref', 'id', 'serial', 'serial_number', 'ttb_id',
    'record', 'row_id'],
};

const LOOKUP = new Map();
for (const [target, names] of Object.entries(ALIASES)) {
  for (const name of names) LOOKUP.set(name, target);
}

export function normalizeHeader(name) {
  const key = String(name || '').trim().toLowerCase()
    .replace(/-/g, '_').replace(/\s+/g, '_');
  return LOOKUP.get(key) || LOOKUP.get(key.replace(/_/g, ' ')) || null;
}

const TRUE_WORDS = new Set(['1', 'true', 'yes', 'y', 't', 'x', 'import', 'imported']);
const FALSE_WORDS = new Set(['0', 'false', 'no', 'n', 'f', '', 'domestic']);

export function toBool(value) {
  const text = String(value ?? '').trim().toLowerCase();
  if (TRUE_WORDS.has(text)) return true;
  if (FALSE_WORDS.has(text)) return false;
  return null;
}

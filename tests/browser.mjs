/**
 * End-to-end tests for the static, browser-only build in web/.
 *
 * Runs a real Chromium against a real static server, so it exercises the
 * whole path: vendored WebAssembly OCR, the ported rules, and the pages.
 *
 *   node tests/browser.mjs
 *
 * Requires Playwright. Skips with a clear message if it is unavailable.
 */
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const WEB = join(ROOT, 'web');
const LABELS = join(ROOT, 'samples', 'labels');
const PORT = Number(process.env.PORT || 8123);

const TYPES = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.wasm': 'application/wasm', '.gz': 'application/gzip',
  '.png': 'image/png', '.json': 'application/json', '.txt': 'text/plain',
  '.md': 'text/markdown',
};

function serve() {
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url, `http://127.0.0.1:${PORT}`);
      let path = normalize(decodeURIComponent(url.pathname));
      if (path.endsWith('/')) path += 'index.html';
      const file = join(WEB, path);
      if (!file.startsWith(WEB)) { response.writeHead(403).end(); return; }
      const body = await readFile(file);
      const headers = { 'Content-Type': TYPES[extname(file)] || 'application/octet-stream' };
      // tesseract.js fetches the model as .gz and expects it raw.
      if (file.endsWith('.traineddata.gz')) headers['Content-Type'] = 'application/octet-stream';
      response.writeHead(200, headers).end(body);
    } catch {
      response.writeHead(404).end('not found');
    }
  });
  return new Promise((resolve) => server.listen(PORT, '127.0.0.1', () => resolve(server)));
}

let chromium;
try {
  const require = createRequire(import.meta.url);
  ({ chromium } = require('/opt/node22/lib/node_modules/playwright'));
} catch {
  try {
    const require = createRequire(import.meta.url);
    ({ chromium } = require('playwright'));
  } catch {
    console.log('SKIP: Playwright is not installed, so the browser tests '
      + 'cannot run. Install it with: npm install -D playwright');
    process.exit(0);
  }
}

const results = [];
function check(name, condition, detail = '') {
  results.push({ name, ok: Boolean(condition), detail });
  console.log(`${condition ? '  ok  ' : 'FAIL  '}${name}${detail ? ` - ${detail}` : ''}`);
}

const BOURBON = {
  bottlerName: 'Old Bridge Distillery',
  bottlerAddress: 'Frankfort, Kentucky',
  brandName: 'Old Bridge',
  beverageClass: 'distilled_spirits',
  classType: 'Kentucky Straight Bourbon Whiskey',
  alcoholContent: '45% ABV',
  netContents: '750 mL',
  width1: '95',
  reference: 'SKU-1001',
};

async function runCheck(page, values, files) {
  await page.goto(`http://127.0.0.1:${PORT}/index.html`, { waitUntil: 'load' });
  for (const [id, value] of Object.entries(values)) {
    if (id === 'beverageClass') await page.selectOption('#beverageClass', value);
    else await page.fill(`#${id}`, value);
  }
  await page.setInputFiles('#image1', files[0]);
  if (files[1]) await page.setInputFiles('#image2', files[1]);
  const started = Date.now();
  await page.click('#submit');
  await page.waitForSelector('#results:not([hidden]) .verdict', { timeout: 240000 });
  return {
    seconds: (Date.now() - started) / 1000,
    verdict: (await page.textContent('.verdict .text')).trim(),
    body: await page.textContent('#results'),
    sub: (await page.textContent('.verdict .sub')).replace(/\s+/g, ' ').trim(),
    thumbnails: await page.$$eval('#results .label-preview img', (n) => n.length),
  };
}

const server = await serve();
const browser = await chromium.launch({ args: ['--no-sandbox'] });
const page = await browser.newPage();
const consoleErrors = [];
page.on('pageerror', (e) => consoleErrors.push(e.message));
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });

try {
  console.log('\nStatic browser build\n');

  // Every page must render.
  for (const name of ['index.html', 'bulk.html', 'help.html']) {
    const response = await page.goto(`http://127.0.0.1:${PORT}/${name}`);
    check(`${name} loads`, response.status() === 200);
  }
  check('the beverage list is populated from the rules',
        (await page.goto(`http://127.0.0.1:${PORT}/index.html`),
         await page.$$eval('#beverageClass option', (o) => o.length)) === 8);

  // A compliant label passes.
  const good = await runCheck(page, BOURBON, [join(LABELS, '01_bourbon_compliant.png')]);
  check('a compliant label passes', good.verdict === 'PASS - everything matches',
        good.verdict);
  check('one picture shows one preview', good.thumbnails === 1);
  check('it does not claim two pictures', !good.sub.includes('2 pictures'));
  console.log(`        (first check, including loading the engine: ${good.seconds.toFixed(1)}s)`);

  // An undersized warning is caught, with the rule cited.
  const tiny = await runCheck(page, {
    brandName: 'Harbor Light', classType: 'India Pale Ale',
    alcoholContent: '6.2% ABV', netContents: '12 fl oz',
    bottlerName: 'Harbor Light Brewing Co.', bottlerAddress: 'Portland, Maine',
    beverageClass: 'malt_beverage', width1: '90',
  }, [join(LABELS, '03_beer_tiny_warning.png')]);
  check('an undersized health warning is caught',
        tiny.verdict === 'PROBLEMS FOUND' && tiny.body.includes('letters are too small'),
        tiny.verdict);
  check('the governing rule is cited', tiny.body.includes('27 CFR 16.22'));
  console.log(`        (second check, engine already loaded: ${tiny.seconds.toFixed(1)}s)`);

  // A missing warning is caught.
  const none = await runCheck(page, {
    brandName: 'Silver Hollow', classType: 'Chardonnay',
    alcoholContent: '13.0% ABV', netContents: '750 mL',
    bottlerName: 'Silver Hollow Cellars', bottlerAddress: 'Sonoma, California',
    beverageClass: 'wine', width1: '100',
  }, [join(LABELS, '04_wine_no_warning.png')]);
  check('a missing health warning is caught',
        none.body.includes('Government Health Warning is missing'), none.verdict);

  // Two panels are checked as one container.
  const pair = await runCheck(page, {
    brandName: 'Ironwood Bend', classType: 'Tennessee Whiskey',
    alcoholContent: '43% ABV', netContents: '750 mL',
    bottlerName: 'Ironwood Bend Distilling Co.',
    bottlerAddress: 'Nashville, Tennessee',
    beverageClass: 'distilled_spirits', width1: '95', width2: '95',
  }, [join(LABELS, '07_whiskey_front.png'), join(LABELS, '07_whiskey_back.png')]);
  check('front and back together pass', pair.verdict === 'PASS - everything matches',
        pair.verdict);
  check('the page says two pictures were combined',
        pair.sub.includes('Checked 2 pictures together as one container'));
  check('it names the panel carrying the warning',
        pair.body.includes('picture 2 (back)'));
  check('two pictures show two previews', pair.thumbnails === 2);

  // The front panel alone is incomplete.
  const frontOnly = await runCheck(page, {
    brandName: 'Ironwood Bend', classType: 'Tennessee Whiskey',
    alcoholContent: '43% ABV', netContents: '750 mL',
    bottlerName: 'Ironwood Bend Distilling Co.',
    bottlerAddress: 'Nashville, Tennessee',
    beverageClass: 'distilled_spirits', width1: '95',
  }, [join(LABELS, '07_whiskey_front.png')]);
  check('the front panel alone is incomplete',
        frontOnly.body.includes('Government Health Warning is missing'),
        frontOnly.verdict);

  // The batch page: a spreadsheet plus all the pictures, matched by name.
  await page.goto(`http://127.0.0.1:${PORT}/bulk.html`, { waitUntil: 'load' });
  await page.setInputFiles('#csvFile', join(ROOT, 'samples', 'sample_batch.csv'));
  await page.setInputFiles('#imageFiles', [
    '01_bourbon_compliant.png', '02_wine_abv_mismatch.png',
    '03_beer_tiny_warning.png', '04_wine_no_warning.png',
    '05_imported_gin_no_origin.png', '06_cider_lowercase_warning.png',
    '07_whiskey_front.png', '07_whiskey_back.png',
  ].map((name) => join(LABELS, name)));
  await page.click('#submit');
  await page.waitForSelector('#results:not([hidden]) table.results', { timeout: 600000 });
  const rows = await page.$$eval('table.results tbody tr', (n) => n.length);
  const batch = await page.textContent('#results');
  check('the batch page checks every row', rows === 7, `${rows} rows`);
  check('the batch finds the ABV tax-class problem',
        batch.includes('crosses the 14% tax class line'));
  check('the batch finds the undersized warning',
        batch.includes('letters are too small'));
  check('the batch offers a results download',
        Boolean(await page.$('#download')));

  check('no uncaught JavaScript errors', consoleErrors.length === 0,
        consoleErrors.slice(0, 2).join(' | '));
} finally {
  await browser.close();
  server.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);

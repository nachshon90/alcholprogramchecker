/**
 * Parity between the Python reference implementation and the JavaScript port.
 *
 * There are now two copies of the compliance logic: labelcheck/ (Python,
 * with 119 tests) and web/js/ (JavaScript, for the static build). Two copies
 * that quietly disagree would be worse than having one, so this runs the
 * same inputs through both and fails on any difference.
 *
 *   node tests/parity.mjs
 */
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));

const ALCOHOL = [
  'ALC. 13.5% BY VOL', '40% ALC/VOL 80 PROOF', '5.2% ABV', 'ALC 5,2% VOL',
  '150% ALC/VOL', '100% AGAVE 40% ALC/VOL', '90 PROOF', 'BOTTLED IN KENTUCKY',
  'ALCOHOL 12% BY VOLUME', '1750 PROOF', '14.4% ALC/VOL',
];
const CONTENTS = [
  '750 mL', '1.75 L', '12 FL. OZ.', '1 PT 9 FL OZ', '25.4 FLOZ (750 ML)',
  '50 cl', '33.8 FL OZ', 'NET CONTENTS 700ML',
];
const MATCHES = [
  ['Old Bridge Distillery', 'SINCE 1897 0LD BRIDGE DISTILLERY KENTUCKY'],
  ['BROOKLYN', 'B R O O K L Y N BREWING'],
  ['Old Bridge Distillery', 'MOUNTAIN CREEK VINEYARDS'],
  ['Harbor Light Brewing Co.', 'HARBOR LIGHT BREWING'],
  ['Kentucky Straight Bourbon Whiskey', 'KENTUCKY STRAIGHT BOURBON WHISKEY'],
  ['Scotland', 'THISTLE ROW DISTILLERS EDINBURGH'],
];
const CLASSES = [
  [null, 'Kentucky Straight Bourbon Whisky', null],
  [null, 'India Pale Ale', null],
  [null, 'Cabernet Sauvignon', null],
  [null, 'Hard Cider', 5.0],
  [null, 'Hard Cider', 8.0],
  ['beer', 'Cabernet Sauvignon', null],
  [null, 'Junmai Ginjo', null],
  [null, 'Something Unknown', null],
];
const VOLUMES = [200, 237, 238, 750, 3000, 3001, 5000, null];

const round = (n) => (n === null || n === undefined ? null : Number(n.toFixed(6)));

async function javascript() {
  const base = `${ROOT}web/js/`;
  const t = await import(`${base}textnorm.js`);
  const r = await import(`${base}rules.js`);
  const hw = await import(`${base}healthwarning.js`);
  return {
    alcohol: ALCOHOL.map((s) => t.parseAlcohol(s)
      .map((e) => [e.kind, round(e.value), round(e.abv)])),
    contents: CONTENTS.map((s) => t.parseNetContents(s)
      .map((e) => [e.source, round(e.ml)])),
    matches: MATCHES.map(([a, b]) => round(t.fieldMatchScore(a, b))),
    coverage: MATCHES.map(([a, b]) => round(t.tokenCoverage(a, b))),
    windows: MATCHES.map(([a, b]) => round(t.bestWindowSimilarity(a, b))),
    classes: CLASSES.map(([s, c, a]) => r.resolveClass(s, c, a)),
    tolerances: CLASSES.map(([s, c, a]) => {
      const rules = r.getRules(r.resolveClass(s, c, a));
      return round(r.abvToleranceFor(rules, a === null ? 13 : a));
    }),
    sizes: VOLUMES.map((v) => {
      const { mm, assumed } = hw.requiredMm(v);
      return [round(mm), assumed];
    }),
    statement: hw.FULL_STATEMENT,
  };
}

function python() {
  const script = `
import json, sys
sys.path.insert(0, ${JSON.stringify(ROOT)})
from labelcheck import healthwarning as hw, rules as r
from labelcheck.textnorm import (parse_alcohol, parse_net_contents,
                                 field_match_score, token_coverage,
                                 best_window_similarity)

# Fed in as JSON rather than Python literals, so JSON null survives.
ALCOHOL = json.loads(r"""${JSON.stringify(ALCOHOL)}""")
CONTENTS = json.loads(r"""${JSON.stringify(CONTENTS)}""")
MATCHES = json.loads(r"""${JSON.stringify(MATCHES)}""")
CLASSES = json.loads(r"""${JSON.stringify(CLASSES)}""")
VOLUMES = json.loads(r"""${JSON.stringify(VOLUMES)}""")

def rnd(n):
    return None if n is None else round(float(n), 6)

def tol(stated, ctype, abv):
    rules = r.get_rules(r.resolve_class(stated, ctype, abv))
    return rnd(rules.abv_tolerance_for(13 if abv is None else abv))

print(json.dumps({
  "alcohol": [[[e["kind"], rnd(e["value"]), rnd(e["abv"])]
               for e in parse_alcohol(s)] for s in ALCOHOL],
  "contents": [[[e["source"], rnd(e["ml"])] for e in parse_net_contents(s)]
               for s in CONTENTS],
  "matches": [rnd(field_match_score(a, b)) for a, b in MATCHES],
  "coverage": [rnd(token_coverage(a, b)) for a, b in MATCHES],
  "windows": [rnd(best_window_similarity(a, b)) for a, b in MATCHES],
  "classes": [r.resolve_class(s, c, a) for s, c, a in CLASSES],
  "tolerances": [tol(s, c, a) for s, c, a in CLASSES],
  "sizes": [[rnd(hw.required_mm(v)[0]), hw.required_mm(v)[2]] for v in VOLUMES],
  "statement": hw.FULL_STATEMENT,
}))
`;
  const run = spawnSync('python3', ['-c', script], { encoding: 'utf8', cwd: ROOT });
  if (run.status !== 0) {
    console.error(run.stderr);
    throw new Error('the Python reference implementation could not be run');
  }
  return JSON.parse(run.stdout);
}

const js = await javascript();
const py = python();

let failures = 0;
for (const key of Object.keys(py)) {
  const a = JSON.stringify(js[key]);
  const b = JSON.stringify(py[key]);
  if (a === b) {
    console.log(`  ok  ${key}`);
  } else {
    failures += 1;
    console.log(`FAIL  ${key}`);
    console.log(`        python: ${b}`);
    console.log(`        js    : ${a}`);
  }
}

console.log(`\n${Object.keys(py).length - failures}/${Object.keys(py).length} `
  + 'groups agree between Python and JavaScript');
process.exit(failures ? 1 : 0);

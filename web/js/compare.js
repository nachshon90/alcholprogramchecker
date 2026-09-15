/**
 * Field-by-field comparison of label artwork against declared details.
 * Port of labelcheck/compare.py.
 *
 * Each check answers three questions separately: does the regulation
 * require this field at all, can we see it, and does it agree? A required
 * field that is absent fails; one we simply could not read is reported as
 * "cannot check", never as a pass.
 */
import { declaredAbv, declaredMl, inferImport } from './application.js';
import { finding, FAIL, PASS, UNKNOWN, WARN } from './findings.js';
import {
  ALCOHOL_CONTENT, BOTTLER_ADDRESS, BOTTLER_NAME, BRAND_NAME, CLASS_TYPE,
  COUNTRY_OF_ORIGIN, FIELD_LABELS, NET_CONTENTS, OPTIONAL, REQUIRED,
  SULFITE_DECLARATION, abvToleranceFor, requirement,
} from './rules.js';
import {
  fieldMatchScore, formatAlcohol, formatMl, normalize, parseAlcohol,
  parseNetContents, significantTokens, tokenCoverage, tokens,
} from './textnorm.js';

export const MATCH_THRESHOLD = 0.86;
export const PRESENCE_THRESHOLD = 0.55;

const STATES = {
  alabama: 'al', alaska: 'ak', arizona: 'az', arkansas: 'ar',
  california: 'ca', colorado: 'co', connecticut: 'ct', delaware: 'de',
  florida: 'fl', georgia: 'ga', hawaii: 'hi', idaho: 'id', illinois: 'il',
  indiana: 'in', iowa: 'ia', kansas: 'ks', kentucky: 'ky', louisiana: 'la',
  maine: 'me', maryland: 'md', massachusetts: 'ma', michigan: 'mi',
  minnesota: 'mn', mississippi: 'ms', missouri: 'mo', montana: 'mt',
  nebraska: 'ne', nevada: 'nv', 'new hampshire': 'nh', 'new jersey': 'nj',
  'new mexico': 'nm', 'new york': 'ny', 'north carolina': 'nc',
  'north dakota': 'nd', ohio: 'oh', oklahoma: 'ok', oregon: 'or',
  pennsylvania: 'pa', 'rhode island': 'ri', 'south carolina': 'sc',
  'south dakota': 'sd', tennessee: 'tn', texas: 'tx', utah: 'ut',
  vermont: 'vt', virginia: 'va', washington: 'wa', 'west virginia': 'wv',
  wisconsin: 'wi', wyoming: 'wy', 'district of columbia': 'dc',
  'puerto rico': 'pr',
};
const STATE_CODES = new Set(Object.values(STATES));
const ADDRESS_NOISE = new Set(['street', 'st', 'avenue', 'ave', 'road', 'rd',
  'drive', 'dr', 'lane', 'ln', 'suite', 'ste', 'unit', 'po', 'box',
  'highway', 'hwy', 'blvd', 'boulevard', 'usa', 'us', 'united', 'states']);

function missingFinding(fieldKey, rules, expected) {
  const level = requirement(rules, fieldKey);
  const label = FIELD_LABELS[fieldKey];
  if (level === REQUIRED) {
    return finding({
      field: fieldKey,
      title: `${label} is missing from the label`,
      status: FAIL,
      detail: `The ${label.toLowerCase()} could not be found anywhere on this `
        + `label. ${rules.displayName} labels must show it. If it appears on `
        + 'another panel of the container, check that panel too.',
      expected,
      found: '(not found on the label)',
      cite: rules.authority,
    });
  }
  return finding({
    field: fieldKey,
    title: `${label} is not visible on the label`,
    status: WARN,
    detail: `The ${label.toLowerCase()} was given in the application but could `
      + 'not be found on the label. It is not always required for this kind of '
      + 'drink, so please check whether it is needed here.',
    expected,
    found: '(not found on the label)',
    cite: rules.authority,
  });
}

function undeclaredFinding(fieldKey, rules) {
  if (requirement(rules, fieldKey) !== REQUIRED) return null;
  const label = FIELD_LABELS[fieldKey];
  return finding({
    field: fieldKey,
    title: `No ${label.toLowerCase()} was given to compare against`,
    status: UNKNOWN,
    detail: `${rules.displayName} labels must show the ${label.toLowerCase()}, `
      + 'but the application data did not include it, so there is nothing to '
      + 'compare the label against. Please fill this in and check again.',
    cite: rules.authority,
  });
}

function excerpt(expected, haystack, span = 60) {
  if (!significantTokens(expected).length) {
    return haystack.length > span ? `${haystack.slice(0, span)}...` : haystack;
  }
  let bestLine = '';
  let bestScore = 0;
  for (const line of haystack.split('\n')) {
    if (!line.trim()) continue;
    const score = fieldMatchScore(expected, line);
    if (score > bestScore) { bestScore = score; bestLine = line; }
  }
  if (bestLine) return bestLine.trim().slice(0, 120);
  return haystack.length > span ? `${haystack.slice(0, span)}...` : haystack;
}

function textField(fieldKey, expected, result, rules) {
  const label = FIELD_LABELS[fieldKey];
  if (!expected || !expected.trim()) {
    const f = undeclaredFinding(fieldKey, rules);
    return f ? [f] : [];
  }
  const score = fieldMatchScore(expected, result.text);
  if (score >= MATCH_THRESHOLD) {
    return [finding({
      field: fieldKey,
      title: `${label} matches`,
      status: PASS,
      detail: `The label shows the same ${label.toLowerCase()} as the application.`,
      expected,
      found: excerpt(expected, result.text),
      cite: rules.authority,
    })];
  }
  if (score < PRESENCE_THRESHOLD) return [missingFinding(fieldKey, rules, expected)];
  return [finding({
    field: fieldKey,
    title: `${label} does not match`,
    status: FAIL,
    detail: `The ${label.toLowerCase()} on the label does not match the `
      + `application. The application says "${expected}". Please compare the `
      + 'two carefully - this may be a spelling difference or a different product.',
    expected,
    found: excerpt(expected, result.text),
    cite: rules.authority,
  })];
}

export const checkBrandName = (app, result, rules) =>
  textField(BRAND_NAME, app.brandName, result, rules);
export const checkClassType = (app, result, rules) =>
  textField(CLASS_TYPE, app.classType, result, rules);
export const checkBottlerName = (app, result, rules) =>
  textField(BOTTLER_NAME, app.bottlerName, result, rules);

export function checkAlcoholContent(app, result, rules) {
  const declared = declaredAbv(app);
  if (declared === null) {
    if (app.alcoholContent && app.alcoholContent.trim()) {
      return [finding({
        field: ALCOHOL_CONTENT,
        title: 'Alcohol content in the application could not be read',
        status: UNKNOWN,
        detail: `The application gives the alcohol content as `
          + `"${app.alcoholContent}", which the tool could not understand. `
          + 'Please write it like "40% ABV" or "80 proof".',
        expected: app.alcoholContent,
        cite: rules.abvToleranceCite,
      })];
    }
    const f = undeclaredFinding(ALCOHOL_CONTENT, rules);
    return f ? [f] : [];
  }

  const candidates = parseAlcohol(result.text);
  if (!candidates.length) {
    return [missingFinding(ALCOHOL_CONTENT, rules, `${declared}% ABV`)];
  }

  const tolerance = abvToleranceFor(rules, declared);
  const best = candidates.reduce((a, b) =>
    (Math.abs(b.abv - declared) < Math.abs(a.abv - declared) ? b : a));
  const difference = Math.abs(best.abv - declared);
  const wineLike = ['wine', 'cider', 'sake', 'mead'].includes(rules.key);
  const crossesTaxClass = wineLike && ((declared > 14.0) !== (best.abv > 14.0));

  if (difference <= tolerance + 1e-9 && !crossesTaxClass) {
    const note = best.kind === 'proof'
      ? ' The label states proof, which matches the declared ABV.' : '';
    return [finding({
      field: ALCOHOL_CONTENT,
      title: 'Alcohol content matches',
      status: PASS,
      detail: `The label shows ${formatAlcohol(best)} and the application `
        + `declares ${declared}% ABV. That is within the allowed difference of `
        + `${tolerance} percentage points.${note}`,
      expected: `${declared}% ABV`,
      found: formatAlcohol(best),
      cite: rules.abvToleranceCite,
    })];
  }

  if (crossesTaxClass) {
    return [finding({
      field: ALCOHOL_CONTENT,
      title: 'Alcohol content crosses the 14% tax class line',
      status: FAIL,
      detail: `The label shows ${formatAlcohol(best)} but the application `
        + `declares ${declared}% ABV. One is above 14% and the other is at or `
        + 'below it. The allowed difference may never be used to move a wine '
        + 'across the 14% line, because the two sides are taxed differently.',
      expected: `${declared}% ABV`,
      found: formatAlcohol(best),
      cite: '27 CFR 4.36(b)',
    })];
  }

  return [finding({
    field: ALCOHOL_CONTENT,
    title: 'Alcohol content does not match',
    status: FAIL,
    detail: `The label shows ${formatAlcohol(best)} but the application `
      + `declares ${declared}% ABV. That is a difference of `
      + `${difference.toFixed(2)} percentage points, and only ${tolerance} is `
      + `allowed for ${rules.displayName.toLowerCase()}.`,
    expected: `${declared}% ABV`,
    found: formatAlcohol(best),
    cite: rules.abvToleranceCite,
  })];
}

export function checkNetContents(app, result, rules) {
  const declared = declaredMl(app);
  if (declared === null) {
    if (app.netContents && app.netContents.trim()) {
      return [finding({
        field: NET_CONTENTS,
        title: 'Net contents in the application could not be read',
        status: UNKNOWN,
        detail: `The application gives the net contents as "${app.netContents}", `
          + 'which the tool could not understand. Please write it like '
          + '"750 mL" or "12 fl oz".',
        expected: app.netContents,
        cite: rules.standardsCite,
      })];
    }
    const f = undeclaredFinding(NET_CONTENTS, rules);
    return f ? [f] : [];
  }

  const findings = [];
  const candidates = parseNetContents(result.text);
  if (!candidates.length) {
    findings.push(missingFinding(NET_CONTENTS, rules, formatMl(declared)));
  } else {
    const best = candidates.reduce((a, b) =>
      (Math.abs(b.ml - declared) < Math.abs(a.ml - declared) ? b : a));
    const allowed = Math.max(1.0, declared * 0.015);
    if (Math.abs(best.ml - declared) <= allowed) {
      findings.push(finding({
        field: NET_CONTENTS,
        title: 'Net contents match',
        status: PASS,
        detail: `The label shows ${best.source} and the application declares `
          + `${formatMl(declared)}. These agree.`,
        expected: formatMl(declared),
        found: best.source,
        cite: rules.authority,
      }));
    } else {
      findings.push(finding({
        field: NET_CONTENTS,
        title: 'Net contents do not match',
        status: FAIL,
        detail: `The label shows ${best.source} (about ${best.ml} mL) but the `
          + `application declares ${formatMl(declared)}. These are different sizes.`,
        expected: formatMl(declared),
        found: best.source,
        cite: rules.authority,
      }));
    }
  }

  // Advisory only: permitted sizes have been amended repeatedly.
  if (rules.standardsOfFillMl.length) {
    const nearest = rules.standardsOfFillMl.reduce((a, b) =>
      (Math.abs(b - declared) < Math.abs(a - declared) ? b : a));
    if (Math.abs(nearest - declared) > 1.0) {
      findings.push(finding({
        field: NET_CONTENTS,
        title: 'Container size is not a standard size',
        status: WARN,
        advisory: true,
        detail: `${formatMl(declared)} is not one of the standard container `
          + `sizes for ${rules.displayName.toLowerCase()}. The nearest standard `
          + `size is ${formatMl(nearest)}. Standard sizes have changed in recent `
          + 'years and some products are exempt, so please confirm this one.',
        expected: `a standard size, nearest is ${formatMl(nearest)}`,
        found: formatMl(declared),
        cite: rules.standardsCite,
      }));
    }
  }
  return findings;
}

export function checkBottlerAddress(app, result, rules) {
  const expected = (app.bottlerAddress || '').trim();
  if (!expected) {
    const f = undeclaredFinding(BOTTLER_ADDRESS, rules);
    return f ? [f] : [];
  }

  const fullScore = fieldMatchScore(expected, result.text);
  const ocrTokens = new Set(tokens(result.text));
  const addressTokens = tokens(expected)
    .filter((t) => !ADDRESS_NOISE.has(t) && !/^\d+$/.test(t));
  const placeTokens = addressTokens.filter((t) => STATES[t] || STATE_CODES.has(t));
  const cityTokens = addressTokens
    .filter((t) => !STATES[t] && !STATE_CODES.has(t) && t.length > 2);

  const present = (token) => {
    if (ocrTokens.has(token)) return true;
    if (STATES[token] && ocrTokens.has(STATES[token])) return true;
    if (STATE_CODES.has(token)) {
      const joined = [...ocrTokens].join(' ');
      for (const [name, code] of Object.entries(STATES)) {
        if (code === token && joined.includes(name)) return true;
      }
    }
    return false;
  };

  const cityFound = cityTokens.length ? cityTokens.some(present) : false;
  const stateFound = placeTokens.length ? placeTokens.some(present) : false;

  if (fullScore >= MATCH_THRESHOLD || (cityFound && stateFound)) {
    return [finding({
      field: BOTTLER_ADDRESS,
      title: 'Bottler / producer address matches',
      status: PASS,
      detail: 'The place of business on the label agrees with the application. '
        + 'Labels often show only the city and state, which is allowed.',
      expected,
      found: excerpt(expected, result.text),
      cite: rules.authority,
    })];
  }

  if (cityFound || stateFound || fullScore >= PRESENCE_THRESHOLD) {
    return [finding({
      field: BOTTLER_ADDRESS,
      title: 'Bottler / producer address only partly matches',
      status: FAIL,
      detail: 'Only part of the address could be matched. The application says '
        + `"${expected}". Please compare the address on the label with the `
        + 'application by eye.',
      expected,
      found: excerpt(expected, result.text),
      cite: rules.authority,
    })];
  }
  return [missingFinding(BOTTLER_ADDRESS, rules, expected)];
}

export function checkCountryOfOrigin(app, result, rules) {
  const expected = (app.countryOfOrigin || '').trim();
  const isImport = inferImport(app);
  if (!isImport && !expected) {
    return [finding({
      field: COUNTRY_OF_ORIGIN,
      title: 'Country of origin not required',
      status: PASS,
      detail: 'This product was not marked as imported, so no country of '
        + 'origin statement is needed.',
      cite: '19 CFR 134',
    })];
  }
  if (!expected) {
    return [finding({
      field: COUNTRY_OF_ORIGIN,
      title: 'No country of origin was given to compare against',
      status: UNKNOWN,
      detail: 'This product is marked as imported, so the label must name the '
        + 'country it came from, but the application did not say which '
        + 'country. Please fill this in and check again.',
      cite: '19 CFR 134',
    })];
  }

  // Presence is judged on whether the country's own words appear, so an
  // absence is not misreported as a mismatch.
  const coverage = tokenCoverage(expected, result.text);
  const score = Math.max(fieldMatchScore(expected, result.text), coverage);
  if (coverage >= 0.5 || score >= MATCH_THRESHOLD) {
    return [finding({
      field: COUNTRY_OF_ORIGIN,
      title: 'Country of origin matches',
      status: PASS,
      detail: `The label names ${expected}, matching the application.`,
      expected,
      found: excerpt(expected, result.text),
      cite: '19 CFR 134',
    })];
  }
  if (coverage < 0.5) {
    return [finding({
      field: COUNTRY_OF_ORIGIN,
      title: 'Country of origin is missing from the label',
      status: FAIL,
      detail: 'This is an imported product, so the label must say that it is a '
        + `product of ${expected}. That statement could not be found.`,
      expected,
      found: '(not found on the label)',
      cite: '19 CFR 134',
    })];
  }
  return [finding({
    field: COUNTRY_OF_ORIGIN,
    title: 'Country of origin does not match',
    status: FAIL,
    detail: `The application says the product comes from ${expected}, but the `
      + 'label appears to say something else.',
    expected,
    found: excerpt(expected, result.text),
    cite: '19 CFR 134',
  })];
}

export function checkSulfites(app, result, rules) {
  const level = requirement(rules, SULFITE_DECLARATION);
  if (level === OPTIONAL && app.containsSulfites !== true) return [];
  if (app.containsSulfites === false) {
    return [finding({
      field: SULFITE_DECLARATION,
      title: 'Sulfite declaration not required',
      status: PASS,
      detail: 'The application states this product is below 10 parts per '
        + 'million of sulfur dioxide, so no sulfite statement is needed.',
      cite: '27 CFR 4.32(e)',
    })];
  }

  const normalized = normalize(result.text);
  if (normalized.includes('contains sulfites')
      || normalized.includes('contains sulphites')) {
    return [finding({
      field: SULFITE_DECLARATION,
      title: 'Sulfite declaration is present',
      status: PASS,
      detail: 'The label carries the words CONTAINS SULFITES.',
      expected: 'CONTAINS SULFITES',
      found: 'CONTAINS SULFITES',
      cite: '27 CFR 4.32(e)',
    })];
  }

  if (level === REQUIRED && app.containsSulfites !== false) {
    return [finding({
      field: SULFITE_DECLARATION,
      title: 'Sulfite declaration is missing',
      status: app.containsSulfites ? FAIL : WARN,
      detail: 'The words CONTAINS SULFITES could not be found on this label. '
        + 'Wine must carry this statement whenever it holds 10 parts per '
        + 'million or more of sulfur dioxide, which covers almost all wine '
        + "sold commercially. If this wine is below that level, set the "
        + 'sulfites box to "no".',
      expected: 'CONTAINS SULFITES',
      found: '(not found on the label)',
      cite: '27 CFR 4.32(e)',
    })];
  }
  return [];
}

/** The declared product details a label is checked against. */
import { getRules, resolveClass } from './rules.js';
import { parseAlcohol, parseNetContents } from './textnorm.js';

export function makeApplication(values = {}) {
  return {
    brandName: '', classType: '', alcoholContent: '', netContents: '',
    bottlerName: '', bottlerAddress: '', countryOfOrigin: '',
    beverageClass: '', isImport: false, containsSulfites: null,
    labelWidthMm: null, labelWidthMm2: null, reference: '',
    imagePath: '', imagePath2: '',
    ...values,
  };
}

export function declaredAbv(app) {
  const parsed = parseAlcohol(app.alcoholContent);
  if (!parsed.length) return null;
  const abv = parsed.find((e) => e.kind === 'abv');
  return abv ? abv.abv : parsed[0].abv;
}

export function declaredMl(app) {
  const parsed = parseNetContents(app.netContents);
  return parsed.length ? parsed[0].ml : null;
}

export function resolvedClass(app) {
  return resolveClass(app.beverageClass, app.classType, declaredAbv(app));
}

export function rulesFor(app) {
  return getRules(resolvedClass(app));
}

const DOMESTIC = new Set(['usa', 'us', 'united states',
                          'united states of america', 'u s a', 'america',
                          'domestic']);

/** An explicit foreign origin implies an import even if the box is unticked. */
export function inferImport(app) {
  if (app.isImport) return true;
  const origin = (app.countryOfOrigin || '').trim().toLowerCase().replace(/\./g, '');
  return Boolean(origin) && !DOMESTIC.has(origin);
}

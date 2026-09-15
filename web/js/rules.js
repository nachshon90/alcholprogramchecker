/**
 * TTB labelling rules by beverage class. Port of labelcheck/rules.py.
 * Citations are to 27 CFR so every decision can be audited.
 */

export const BRAND_NAME = 'brand_name';
export const CLASS_TYPE = 'class_type';
export const ALCOHOL_CONTENT = 'alcohol_content';
export const NET_CONTENTS = 'net_contents';
export const BOTTLER_NAME = 'bottler_name';
export const BOTTLER_ADDRESS = 'bottler_address';
export const COUNTRY_OF_ORIGIN = 'country_of_origin';
export const SULFITE_DECLARATION = 'sulfite_declaration';
export const HEALTH_WARNING = 'health_warning';

export const FIELD_LABELS = {
  [BRAND_NAME]: 'Brand name',
  [CLASS_TYPE]: 'Class / type',
  [ALCOHOL_CONTENT]: 'Alcohol content',
  [NET_CONTENTS]: 'Net contents',
  [BOTTLER_NAME]: 'Bottler / producer name',
  [BOTTLER_ADDRESS]: 'Bottler / producer address',
  [COUNTRY_OF_ORIGIN]: 'Country of origin',
  [SULFITE_DECLARATION]: 'Sulfite declaration',
  [HEALTH_WARNING]: 'Government Health Warning',
};

export const FIELD_ORDER = [
  BRAND_NAME, CLASS_TYPE, ALCOHOL_CONTENT, NET_CONTENTS,
  BOTTLER_NAME, BOTTLER_ADDRESS, COUNTRY_OF_ORIGIN,
  SULFITE_DECLARATION, HEALTH_WARNING,
];

export const REQUIRED = 'required';
export const CONDITIONAL = 'conditional';
export const OPTIONAL = 'optional';

// Standards of fill in millilitres, per T.D. TTB-165 (2020). Held as data
// because they have been amended repeatedly; findings driven by them are
// advisory, never hard failures.
const SPIRITS_FILL = [1800, 1750, 1000, 945, 900, 750, 720, 700, 500, 375,
                      355, 200, 100, 50];
const WINE_FILL = [3000, 1500, 1000, 750, 720, 700, 620, 600, 568, 500, 375,
                   355, 250, 200, 187, 100, 50];

const MALT_REQS = {
  [BRAND_NAME]: REQUIRED,            // 27 CFR 7.63(a)
  [CLASS_TYPE]: REQUIRED,            // 27 CFR 7.63(b)
  [NET_CONTENTS]: REQUIRED,          // 27 CFR 7.63(d)
  [BOTTLER_NAME]: REQUIRED,          // 27 CFR 7.66
  [BOTTLER_ADDRESS]: REQUIRED,       // 27 CFR 7.66
  [ALCOHOL_CONTENT]: CONDITIONAL,    // 27 CFR 7.65 - optional federally
  [COUNTRY_OF_ORIGIN]: CONDITIONAL,
  [SULFITE_DECLARATION]: CONDITIONAL,
  [HEALTH_WARNING]: REQUIRED,        // 27 CFR 16.21
};

const WINE_REQS = {
  [BRAND_NAME]: REQUIRED,            // 27 CFR 4.32(a)(1)
  [CLASS_TYPE]: REQUIRED,            // 27 CFR 4.32(a)(2)
  [ALCOHOL_CONTENT]: REQUIRED,       // 27 CFR 4.32(a)(3), 4.36
  [NET_CONTENTS]: REQUIRED,          // 27 CFR 4.32(a)(4)
  [BOTTLER_NAME]: REQUIRED,          // 27 CFR 4.35
  [BOTTLER_ADDRESS]: REQUIRED,       // 27 CFR 4.35
  [COUNTRY_OF_ORIGIN]: CONDITIONAL,
  [SULFITE_DECLARATION]: REQUIRED,   // 27 CFR 4.32(e)
  [HEALTH_WARNING]: REQUIRED,
};

const SPIRITS_REQS = {
  [BRAND_NAME]: REQUIRED,            // 27 CFR 5.63(a)
  [CLASS_TYPE]: REQUIRED,            // 27 CFR 5.63(b), 5.141
  [ALCOHOL_CONTENT]: REQUIRED,       // 27 CFR 5.63(c), 5.65
  [NET_CONTENTS]: REQUIRED,          // 27 CFR 5.63(d)
  [BOTTLER_NAME]: REQUIRED,          // 27 CFR 5.66
  [BOTTLER_ADDRESS]: REQUIRED,       // 27 CFR 5.66
  [COUNTRY_OF_ORIGIN]: CONDITIONAL,
  [SULFITE_DECLARATION]: OPTIONAL,
  [HEALTH_WARNING]: REQUIRED,
};

// Outside the FAA Act: FDA labelling applies, but 27 CFR Part 16 still
// reaches every beverage at or above 0.5% ABV.
const FDA_REQS = {
  [BRAND_NAME]: REQUIRED,
  [CLASS_TYPE]: REQUIRED,
  [ALCOHOL_CONTENT]: CONDITIONAL,
  [NET_CONTENTS]: REQUIRED,          // 21 CFR 101.105
  [BOTTLER_NAME]: REQUIRED,          // 21 CFR 101.5
  [BOTTLER_ADDRESS]: REQUIRED,
  [COUNTRY_OF_ORIGIN]: CONDITIONAL,
  [SULFITE_DECLARATION]: CONDITIONAL,
  [HEALTH_WARNING]: REQUIRED,        // 27 CFR 16.21
};

const WINE_TOLERANCE = {
  abvTolerance: 1.5,
  abvToleranceHigh: 1.0,
  abvHighThreshold: 14.0,
  abvToleranceCite: '27 CFR 4.36(b)',
};

export const RULES = {
  malt_beverage: {
    key: 'malt_beverage',
    displayName: 'Malt beverage',
    plainName: 'Beer or other malt beverage',
    authority: '27 CFR Part 7',
    abvTolerance: 0.3,
    abvToleranceCite: '27 CFR 7.71',
    standardsOfFillMl: [],
    standardsCite: 'No federal standard of fill for malt beverages',
    requirements: MALT_REQS,
    faaActCovered: true,
  },
  wine: {
    key: 'wine',
    displayName: 'Wine',
    plainName: 'Wine',
    authority: '27 CFR Part 4',
    ...WINE_TOLERANCE,
    standardsOfFillMl: WINE_FILL,
    standardsCite: '27 CFR 4.72',
    requirements: WINE_REQS,
    faaActCovered: true,
  },
  distilled_spirits: {
    key: 'distilled_spirits',
    displayName: 'Distilled spirits',
    plainName: 'Liquor or spirits',
    authority: '27 CFR Part 5',
    abvTolerance: 0.15,
    abvToleranceCite: '27 CFR 5.65(a)',
    standardsOfFillMl: SPIRITS_FILL,
    standardsCite: '27 CFR 5.203',
    requirements: SPIRITS_REQS,
    faaActCovered: true,
  },
  cider: {
    key: 'cider',
    displayName: 'Hard cider',
    plainName: 'Hard cider',
    authority: '27 CFR Part 4 (wine) at or above 7% ABV',
    ...WINE_TOLERANCE,
    standardsOfFillMl: WINE_FILL,
    standardsCite: '27 CFR 4.72',
    requirements: WINE_REQS,
    faaActCovered: true,
  },
  sake: {
    key: 'sake',
    displayName: 'Sake',
    plainName: 'Sake (rice wine)',
    authority: '27 CFR Part 4',
    ...WINE_TOLERANCE,
    standardsOfFillMl: WINE_FILL,
    standardsCite: '27 CFR 4.72',
    requirements: WINE_REQS,
    faaActCovered: true,
  },
  mead: {
    key: 'mead',
    displayName: 'Mead / honey wine',
    plainName: 'Mead (honey wine)',
    authority: '27 CFR Part 4',
    ...WINE_TOLERANCE,
    standardsOfFillMl: WINE_FILL,
    standardsCite: '27 CFR 4.72',
    requirements: WINE_REQS,
    faaActCovered: true,
  },
  fda_regulated: {
    key: 'fda_regulated',
    displayName: 'Non-FAA Act beverage (FDA-labelled)',
    plainName: 'Other alcoholic drink (under 7% alcohol)',
    authority: '21 CFR Part 101; 27 CFR Part 16 for the health warning',
    abvTolerance: 0.3,
    abvToleranceCite: 'FDA labelling practice',
    standardsOfFillMl: [],
    standardsCite: 'No federal standard of fill',
    requirements: FDA_REQS,
    faaActCovered: false,
  },
};

export const DEFAULT_CLASS = 'distilled_spirits';

const CLASS_KEYWORDS = [
  ['cider', ['hard cider', 'cider', 'cyder', 'perry']],
  ['sake', ['sake', 'saké', 'junmai', 'ginjo', 'nihonshu']],
  ['mead', ['mead', 'honey wine', 'melomel', 'braggot']],
  ['malt_beverage', ['malt beverage', 'flavored malt', 'beer', 'ale', 'lager',
    'stout', 'porter', 'pilsner', 'pilsener', 'ipa', 'india pale',
    'hard seltzer', 'bock', 'saison', 'hefeweizen', 'kolsch', 'gose',
    'wheat beer']],
  ['distilled_spirits', ['distilled spirits', 'neutral spirits', 'whisky',
    'whiskey', 'bourbon', 'rye', 'scotch', 'vodka', 'gin', 'rum', 'brandy',
    'cognac', 'armagnac', 'tequila', 'mezcal', 'liqueur', 'cordial',
    'schnapps', 'absinthe', 'grappa', 'aquavit', 'akvavit', 'soju', 'shochu',
    'baijiu', 'pisco']],
  ['wine', ['wine', 'champagne', 'sparkling', 'prosecco', 'cava', 'port',
    'sherry', 'madeira', 'vermouth', 'chardonnay', 'cabernet', 'merlot',
    'pinot', 'riesling', 'sauvignon', 'zinfandel', 'syrah', 'shiraz',
    'malbec', 'tempranillo', 'sangiovese', 'moscato', 'rose', 'rosé']],
];

const CLASS_ALIASES = {
  beer: 'malt_beverage', malt: 'malt_beverage',
  'malt beverage': 'malt_beverage', maltbeverage: 'malt_beverage',
  spirits: 'distilled_spirits', spirit: 'distilled_spirits',
  liquor: 'distilled_spirits', distilled: 'distilled_spirits',
  'distilled spirit': 'distilled_spirits',
  'distilled spirits': 'distilled_spirits',
  'hard cider': 'cider', wine: 'wine', cider: 'cider',
  sake: 'sake', mead: 'mead', other: 'fda_regulated',
  fda: 'fda_regulated', 'non-alcoholic': 'fda_regulated',
};

export function resolveClass(stated, classTypeText, abv) {
  let key = null;
  if (stated) {
    const cleaned = String(stated).trim().toLowerCase().replace(/_/g, ' ');
    const underscored = cleaned.replace(/ /g, '_');
    if (RULES[underscored]) key = underscored;
    else if (CLASS_ALIASES[cleaned]) key = CLASS_ALIASES[cleaned];
  }

  if (key === null && classTypeText) {
    const haystack = String(classTypeText).toLowerCase();
    for (const [candidate, words] of CLASS_KEYWORDS) {
      if (words.some((w) => haystack.includes(w))) { key = candidate; break; }
    }
  }

  if (key === null) key = DEFAULT_CLASS;

  // Cider below 7% ABV leaves the FAA Act and is labelled under FDA rules.
  if (key === 'cider' && abv !== null && abv !== undefined && abv < 7.0) {
    return 'fda_regulated';
  }
  return key;
}

export function getRules(key) {
  return RULES[key] || RULES[DEFAULT_CLASS];
}

export function abvToleranceFor(rules, abv) {
  if (rules.abvToleranceHigh !== undefined
      && rules.abvHighThreshold !== undefined
      && abv !== null && abv !== undefined
      && abv > rules.abvHighThreshold) {
    return rules.abvToleranceHigh;
  }
  return rules.abvTolerance;
}

export function requirement(rules, fieldKey) {
  return rules.requirements[fieldKey] || OPTIONAL;
}

export function classChoices() {
  return ['malt_beverage', 'wine', 'distilled_spirits', 'cider', 'sake',
          'mead', 'fda_regulated'].map((k) => [k, RULES[k].plainName]);
}

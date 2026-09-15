/** A single finding: one check, one verdict, in plain English. */
export const PASS = 'pass';
export const FAIL = 'fail';
export const WARN = 'warn';
export const UNKNOWN = 'unknown';

export const SEVERITY_ORDER = { [FAIL]: 0, [UNKNOWN]: 1, [WARN]: 2, [PASS]: 3 };

export const STATUS_WORDS = {
  [PASS]: 'MATCH',
  [FAIL]: 'PROBLEM',
  [WARN]: 'CHECK BY HAND',
  [UNKNOWN]: 'CANNOT CHECK',
};

export function finding({ field, title, status, detail, expected = null,
                          found = null, cite = null, advisory = false }) {
  return { field, title, status, detail, expected, found, cite, advisory };
}

export function worst(findings) {
  if (!findings.length) return UNKNOWN;
  return findings.reduce((acc, f) => (
    SEVERITY_ORDER[f.status] < SEVERITY_ORDER[acc] ? f.status : acc
  ), PASS);
}

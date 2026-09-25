/** Display-only formatting for clinical record text. Nothing here touches stored data --
 * the API returns whatever the provider's EHR sent, and these only change how it reads.
 */

// Tokens that must stay upper-case after title-casing. Lab panels and immunizations are
// dense with these, and "Ldl" or "Covid" reads as a typo.
const ACRONYMS = new Set([
  'ADHD', 'ALT', 'AST', 'BMI', 'BMP', 'BP', 'BUN', 'CBC', 'CMP', 'COPD', 'COVID', 'CO2', 'CT',
  'DTAP', 'ECG', 'EGFR', 'EKG', 'GERD', 'GFR', 'HBA1C', 'HCT', 'HDL', 'HGB', 'HIV', 'HPV',
  'HR', 'IGA', 'IGE', 'IGG', 'IGM', 'II', 'III', 'INR', 'IV', 'LDL', 'MCH', 'MCHC', 'MCV',
  'MMR', 'MPV', 'MRI', 'NOS', 'PCR', 'PSA', 'RBC', 'RDW', 'RSV', 'SARS', 'TDAP', 'TSH', 'UA',
  'VLDL', 'WBC',
])

// Joining words stay lower-case unless they open the string.
const MINOR_WORDS = new Set(['a', 'an', 'and', 'as', 'at', 'by', 'for', 'in', 'of', 'on', 'or', 'the', 'to', 'with'])

function caseWord(word: string, isFirst: boolean): string {
  const upper = word.toUpperCase()
  if (ACRONYMS.has(upper)) return upper
  // Anything with a digit is a code or a measurement ("A1C", "H1N1", "2ND") -- leave it.
  if (/\d/.test(word)) return word
  // The article "a" mid-sentence is a minor word, not an initial.
  if (!isFirst && word === 'A') return 'a'
  // A lone initial, as in a genus abbreviation ("E. COLI") -- keep the capital.
  if (/^[A-Z]$/.test(word)) return word
  // No vowels means an abbreviation the list above doesn't know ("DLDL", "PTT"), not a
  // word -- "Dldl" would read as a typo.
  if (/^[A-Z]+$/.test(word) && !/[AEIOUY]/.test(word)) return word
  const lower = word.toLowerCase()
  if (!isFirst && MINOR_WORDS.has(lower)) return lower
  return lower.charAt(0).toUpperCase() + lower.slice(1)
}

/** Title-cases text that arrived in ALL CAPS ("VITAMIN D, 25-HYDROXY" ->
 * "Vitamin D, 25-Hydroxy"), keeping known acronyms, codes and initials upper-case.
 * Text that already has any lower-case letter is returned untouched: it was written in
 * mixed case on purpose, and re-casing it would only lose information.
 */
export function displayClinicalText(text: string): string {
  if (/[a-z]/.test(text)) return text
  let isFirst = true
  // Split on letter/digit runs so punctuation -- parentheses, hyphens, slashes, commas --
  // passes through exactly as sent. An apostrophe inside a word stays part of it, so a
  // possessive becomes "Children's", not "Children'S".
  return text.replace(/[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*/g, (word) => {
    const cased = caseWord(word, isFirst)
    isFirst = false
    return cased
  })
}

// UCUM spells a few units with bracketed annotations that no one writes by hand; blood
// pressure's "mm[Hg]" is the one this export actually carries, and "120/80 mm[Hg]" reads
// like a parsing bug. Anything not listed is shown exactly as the EHR sent it -- guessing
// at unfamiliar units would be worse than a literal one.
const UCUM_DISPLAY: Record<string, string> = {
  'mm[Hg]': 'mmHg',
  'cm[H2O]': 'cmH₂O',
}

/** A unit as it should read on screen. */
export function displayUnit(unit: string | null): string | null {
  return unit == null ? null : (UCUM_DISPLAY[unit] ?? unit)
}

/** The single value every item shares, or undefined when they differ (or there is at most
 * one item, where "shared" says nothing). Used to state a repeated value once per section.
 */
export function sharedValue<T, V>(items: T[], pick: (item: T) => V): V | undefined {
  if (items.length < 2) return undefined
  const first = pick(items[0])
  return items.every((item) => pick(item) === first) ? first : undefined
}

/** Splits items into groups that share the same key (in first-seen order) of at least
 * `minSize`, plus everything else. Used to pull a run of near-identical rows -- a panel of
 * results from one test, all with the same outcome and date -- out of a table so the shared
 * facts can be stated once.
 */
export function groupRepeated<T>(
  items: T[],
  key: (item: T) => string,
  minSize: number,
): { groups: { key: string; items: T[] }[]; rest: T[] } {
  const byKey = new Map<string, T[]>()
  for (const item of items) {
    const k = key(item)
    byKey.set(k, [...(byKey.get(k) ?? []), item])
  }
  const groups = [...byKey.entries()]
    .filter(([, members]) => members.length >= minSize)
    .map(([k, members]) => ({ key: k, items: members }))
  const grouped = new Set(groups.map((g) => g.key))
  return { groups, rest: items.filter((item) => !grouped.has(key(item))) }
}

export type RangeFlag = 'low' | 'high' | null

// A text-only range that is nothing but one comparator and a number ("<=159", ">= 40",
// "< 5.7"). Anything looser ("Negative", "See comment", "Adult: 0-99") is left as text --
// guessing at those could flag a normal result.
const COMPARATOR_RANGE = /^\s*(<=|>=|<|>|≤|≥)\s*(\d+(?:\.\d+)?)\s*$/

interface Bounds {
  low: number | null
  high: number | null
  /** True for "<" / ">": the bound itself is out of range. FHIR low/high are inclusive. */
  strict: boolean
}

/** Numeric bounds from a text-only comparator range, or null when the text isn't one. */
export function boundsFromRangeText(text: string | null): Bounds | null {
  const match = text ? COMPARATOR_RANGE.exec(text) : null
  if (!match) return null
  const [, op, number] = match
  const bound = Number(number)
  const strict = op === '<' || op === '>'
  return op === '<' || op === '<=' || op === '≤'
    ? { low: null, high: bound, strict }
    : { low: bound, high: null, strict }
}

/** Whether a numeric result falls outside its reference range. Uses the range's numeric
 * bounds, falling back to a plain comparator in its text. Only flags when the range's unit
 * matches the value's (or the range states none): comparing mg/dL against mmol/L bounds
 * would flag -- or clear -- results for the wrong reason.
 */
export function rangeFlag(
  value: number | null,
  valueUnit: string | null,
  range: { low: number | null; high: number | null; unit: string | null; text: string | null } | null,
): RangeFlag {
  if (value == null || range == null) return null
  // Compared after normalizing, since a value and its own range can be spelled differently
  // ("mmHg" against "mm[Hg]") -- that difference isn't a real unit mismatch, and treating it
  // as one would silently stop flagging the result.
  const rangeUnit = displayUnit(range.unit)
  const unit = displayUnit(valueUnit)
  if (rangeUnit != null && unit != null && rangeUnit !== unit) return null
  const bounds: Bounds | null =
    range.low != null || range.high != null
      ? { low: range.low, high: range.high, strict: false }
      : boundsFromRangeText(range.text)
  if (!bounds) return null
  const below = (bound: number) => (bounds.strict ? value <= bound : value < bound)
  const above = (bound: number) => (bounds.strict ? value >= bound : value > bound)
  if (bounds.low != null && below(bounds.low)) return 'low'
  if (bounds.high != null && above(bounds.high)) return 'high'
  return null
}

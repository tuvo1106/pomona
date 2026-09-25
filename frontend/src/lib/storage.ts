/** localStorage that can't take the page down.
 *
 * Every access is wrapped: reading or writing throws outright in a private window, with
 * site data blocked, or once the origin's quota is full, and `JSON.parse` throws on
 * anything another version of this app (or a person with devtools open) left behind. None
 * of what's stored here is data the app can't do without -- it's remembered UI state -- so
 * a failure means "fall back to the default", never an error the user has to see.
 */

export function readStoredJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    return raw == null ? null : (JSON.parse(raw) as T)
  } catch {
    return null
  }
}

export function writeStoredJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Nothing to do and nothing worth saying: the preference just won't outlive the tab.
  }
}

/** A stored array of strings, or null when it's absent or isn't that shape. Guards the
 * element type too -- `JSON.parse` is happy to hand back `[1, null]` for a key that used to
 * hold something else.
 */
export function readStoredStringArray(key: string): string[] | null {
  const value = readStoredJson<unknown>(key)
  if (!Array.isArray(value)) return null
  return value.every((item) => typeof item === 'string') ? (value as string[]) : null
}

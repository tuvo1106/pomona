import { useCallback, useState } from 'react'
import { readStoredJson, writeStoredJson } from '@/lib/storage'

const STORAGE_KEY = 'pomona-basemap'

/** Whether the routes map loads its tile background, remembered per browser.
 *
 * **Off by default, deliberately.** Tiles are the only request this app makes outside its own
 * origin (ADR-0004), and the squares it asks for are the ones your routes are in -- so a
 * default install of a health dashboard would tell a third party roughly where you run,
 * before you had chosen anything. Opting in is a decision a reader can make once they know;
 * a default can't be.
 *
 * It also keeps the project inside the terms it relies on. OpenStreetMap offers those tiles
 * for low-volume personal use, which one person's dashboard is and a widely installed app is
 * not. Off by default means most installs never ask for a tile at all.
 *
 * Tracks still draw either way: the shape of a run is in the GPX, not the basemap.
 */
export function useBasemapEnabled(): [boolean, (next: boolean) => void] {
  // Through lib/storage, not localStorage directly: both halves of that API throw outright in
  // a private window, with site data blocked, or on a full origin quota -- and the write here
  // happens inside a click handler, where an exception would take out the render rather than
  // just lose the preference. `=== true` rather than a cast because anything unparseable or
  // of another shape should land on "off", the same answer as no stored value at all.
  const [enabled, setEnabled] = useState(() => readStoredJson<boolean>(STORAGE_KEY) === true)

  const set = useCallback((next: boolean) => {
    writeStoredJson(STORAGE_KEY, next)
    setEnabled(next)
  }, [])

  return [enabled, set]
}

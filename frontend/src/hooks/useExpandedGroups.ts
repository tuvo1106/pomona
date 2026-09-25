import { useCallback, useEffect, useState } from 'react'
import { readStoredStringArray, writeStoredJson } from '@/lib/storage'

const STORAGE_KEY = 'pomona-expanded-metric-groups'

/** Which metric groups are showing all of their charts rather than the first few.
 *
 * Remembered across visits, because the choice is about how this person wants to read their
 * own dashboard -- someone who tracks running shouldn't have to re-open that section every
 * time. Stored as the expanded ids rather than a "show everything" flag so a group added to
 * metricGroups.ts later starts collapsed like any other, instead of silently inheriting a
 * decision made before it existed.
 */
export function useExpandedGroups() {
  const [expandedGroups, setExpandedGroups] = useState<ReadonlySet<string>>(
    () => new Set(readStoredStringArray(STORAGE_KEY) ?? []),
  )

  useEffect(() => {
    writeStoredJson(STORAGE_KEY, [...expandedGroups])
  }, [expandedGroups])

  const toggleGroup = useCallback((groupId: string) => {
    setExpandedGroups((previous) => {
      const next = new Set(previous)
      if (!next.delete(groupId)) next.add(groupId)
      return next
    })
  }, [])

  /** Adds to what's already expanded rather than replacing it. "Show all charts" can only
   * name the groups with something hidden *in the current range*, so replacing would
   * quietly collapse a group the user expanded under a longer range and that this range
   * happens to show in full -- a collapse they never asked for, noticed only on going back.
   */
  const expandGroups = useCallback((groupIds: string[]) => {
    setExpandedGroups((previous) => new Set([...previous, ...groupIds]))
  }, [])

  const collapseAll = useCallback(() => {
    setExpandedGroups(new Set())
  }, [])

  return { expandedGroups, toggleGroup, expandGroups, collapseAll }
}

import { useEffect, useState } from 'react'

/** Fallback until the header is measured, and the value used if it can't be found at all.
 * Close to the real height, so a first paint at this value doesn't visibly jump.
 */
const FALLBACK_OFFSET = 57

/** How far down the viewport the app's sticky header reaches, in pixels.
 *
 * Measured rather than written as a constant: the header grows at the `sm` breakpoint (its
 * wordmark goes from text-base to text-lg), so a hardcoded number is right at one width and
 * wrong at the other -- and it would silently drift the next time the header changes, which
 * has already happened once. Anything that has to sit below the header (a second sticky bar,
 * the scroll-margin on a section being jumped to) takes its offset from here.
 */
export function useStickyHeaderOffset(): number {
  const [offset, setOffset] = useState(FALLBACK_OFFSET)

  useEffect(() => {
    const header = document.querySelector('header')
    if (!header) return

    const measure = () => setOffset(header.getBoundingClientRect().height || FALLBACK_OFFSET)
    measure()

    // Catches the breakpoint change, and a wrapped header at any width in between.
    const observer = new ResizeObserver(measure)
    observer.observe(header)
    return () => observer.disconnect()
  }, [])

  return offset
}

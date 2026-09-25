import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react'
import { cn } from '@/lib/utils'

export interface NavSection {
  /** The id of the element to scroll to; also what marks this entry current. */
  id: string
  label: string
  /** The group's hue, shown as a dot -- never as the label's text color (see ChartTooltip). */
  color: string
  count: number
}

/** Slack past where a clicked section comes to rest, so the section a jump just landed on
 * counts as current rather than sitting a hair above the line. Also absorbs sub-pixel
 * rounding, which would otherwise flicker a heading resting exactly on the line.
 */
const ACTIVE_SLACK = 4

/** Long enough for a smooth scroll to land. While a click is in flight the spy is paused,
 * so the sections passing under the header on the way don't light up in turn.
 */
const CLICK_LOCK_MS = 700

/** How long to give a smooth scroll to start moving before jumping instead. A smooth scroll
 * runs on the browser's frame loop, and a *hidden* document -- a backgrounded tab, a
 * minimised or occluded window -- has that loop suspended entirely, so `scrollIntoView`
 * reports success and simply never moves. Landing instantly is a worse jump than an
 * animated one; not moving at all is a broken link. (See "Verifying your work" in
 * docs/UI-BACKLOG.md: the same suspension is why a chart screenshotted from an
 * automation-driven browser can look half-drawn.)
 */
const SCROLL_STALL_MS = 250

function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

/** The in-page section nav for the dashboard's trends: sticky under the app header, with
 * the section you're looking at marked as you scroll.
 *
 * `offset` is where the app header ends (useStickyHeaderOffset) -- this bar sticks to that
 * line, and the sections themselves carry a matching scroll-margin so a clicked heading
 * lands below both bars rather than underneath them.
 */
export function SectionNav({
  sections,
  offset,
  scrollGap,
  onStickyHeightChange,
}: {
  sections: NavSection[]
  offset: number
  /** The gap the caller leaves between this bar and a section it scrolls to (its
   * `scroll-margin-top` above this bar's bottom edge). The current-section line is set from
   * it, so the two can't drift into disagreeing about whether a section just jumped to is
   * the one you're on.
   */
  scrollGap: number
  /** This bar's own height, reported so the sections it scrolls to can clear it. */
  onStickyHeightChange?: (height: number) => void
}) {
  const [activeId, setActiveId] = useState<string | null>(null)
  const navRef = useRef<HTMLElement>(null)
  const sizeObserver = useRef<ResizeObserver | null>(null)
  const [stickyHeight, setStickyHeight] = useState(0)
  /** Raised on click and dropped once the scroll has landed; the spy sits out in between. */
  const isJumping = useRef(false)
  const jumpTimer = useRef<number | undefined>(undefined)
  const stallTimer = useRef<number | undefined>(undefined)
  /** The current spy, so the click lock can re-run it the moment it lifts. */
  const pickRef = useRef<() => void>(() => {})

  useEffect(
    () => () => {
      window.clearTimeout(jumpTimer.current)
      window.clearTimeout(stallTimer.current)
    },
    [],
  )

  // This bar covers the top of whatever is under it, so it has to know its own height:
  // the line a section becomes current at is the bottom of *this* bar, not of the app
  // header. Measured, because the pills wrap to a second row on a narrow screen.
  //
  // A callback ref rather than an effect over `stickyRef`: this component renders null
  // until the sections arrive, so an effect with an empty dep list runs once against
  // nothing and never measures the bar that appears a moment later.
  const measureSticky = useCallback((node: HTMLDivElement | null) => {
    sizeObserver.current?.disconnect()
    sizeObserver.current = null
    if (!node) return
    const measure = () => setStickyHeight(node.getBoundingClientRect().height)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    sizeObserver.current = observer
  }, [])

  useEffect(() => () => sizeObserver.current?.disconnect(), [])

  useEffect(() => {
    onStickyHeightChange?.(stickyHeight)
  }, [stickyHeight, onStickyHeightChange])

  useEffect(() => {
    if (sections.length === 0) return
    const line = offset + stickyHeight + scrollGap + ACTIVE_SLACK

    const pick = () => {
      if (isJumping.current) return
      // The last section whose top has crossed the line: the one filling the screen below
      // the bars. Decided from rects, never from an observer's entries -- a section taller
      // than the viewport is simply "intersecting" for its whole length, which says nothing
      // about whether you are in it or in the one above.
      let current = sections[0].id
      for (const section of sections) {
        const element = document.getElementById(section.id)
        if (element && element.getBoundingClientRect().top <= line) {
          current = section.id
        }
      }
      setActiveId(current)
    }
    pickRef.current = pick

    // Scroll drives this, not an IntersectionObserver. An observer only fires when a
    // section *fully* enters or leaves, and consecutive sections are 32px apart
    // (`space-y-8`), so scrolling from one tall expanded group into the next produces no
    // event at all until a third section appears from the bottom -- the pill can lag a
    // whole section for hundreds of pixels. Browsers already cap scroll events at one per
    // frame, and `pick` is a handful of rect reads, so this needs no throttling of its own.
    // Deliberately not rAF-throttled: rAF is the loop that stops dead in a hidden document
    // (see SCROLL_STALL_MS above), and the spy going quiet is the failure this replaced.
    window.addEventListener('scroll', pick, { passive: true })
    window.addEventListener('resize', pick)

    // Layout can move a section without any scrolling -- expanding a group, a range change
    // shortening one. The observer earns its place there, as a "something moved" trigger.
    const observer = new IntersectionObserver(pick, {
      rootMargin: `-${offset + stickyHeight}px 0px 0px 0px`,
      threshold: [0, 1],
    })
    for (const section of sections) {
      const element = document.getElementById(section.id)
      if (element) observer.observe(element)
    }
    pick()

    return () => {
      window.removeEventListener('scroll', pick)
      window.removeEventListener('resize', pick)
      observer.disconnect()
    }
  }, [sections, offset, stickyHeight, scrollGap])

  // Below `sm` the bar scrolls sideways, so the current pill can sit off-screen with
  // nothing to say the nav continues. 'nearest' on both axes: a nav that isn't overflowing
  // -- the usual case -- doesn't move, and the page never scrolls vertically for this.
  useEffect(() => {
    const nav = navRef.current
    if (!nav || !activeId || nav.scrollWidth <= nav.clientWidth) return
    nav
      .querySelector('[aria-current="location"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [activeId])

  if (sections.length === 0) return null

  const jumpTo = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    const element = document.getElementById(id)
    if (!element) return // Let the browser follow the href rather than swallowing the click.
    event.preventDefault()
    setActiveId(id)
    isJumping.current = true
    window.clearTimeout(jumpTimer.current)
    jumpTimer.current = window.setTimeout(() => {
      isJumping.current = false
      // A long jump can still be travelling when the lock lifts, and the scroll may settle
      // without another event; re-read the position rather than trusting where it got to.
      pickRef.current()
    }, CLICK_LOCK_MS)

    const startY = window.scrollY
    element.scrollIntoView({
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
      block: 'start',
    })
    // If nothing has moved by now the animation never started, so jump. Comparing against
    // the starting position also means a user who scrolled away in the meantime isn't
    // yanked back: their scroll counts as movement and this does nothing.
    window.clearTimeout(stallTimer.current)
    stallTimer.current = window.setTimeout(() => {
      if (window.scrollY === startY) {
        element.scrollIntoView({ behavior: 'auto', block: 'start' })
      }
    }, SCROLL_STALL_MS)
  }

  return (
    // Sticky inside the trends section, so the bar leaves with it rather than following the
    // page down over the workouts and diagnostics below. Translucent like the app header,
    // and under it (z-10) so it slides beneath rather than over.
    <div
      ref={measureSticky}
      className="bg-background/95 supports-[backdrop-filter]:bg-background/80 sticky z-[5] -mx-1 px-1 py-2 backdrop-blur"
      style={{ top: offset }}
    >
      <nav
        ref={navRef}
        aria-label="Metric sections"
        className="-m-1 flex items-center gap-1.5 overflow-x-auto p-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {sections.map((section) => {
          const isActive = section.id === activeId
          return (
            <a
              key={section.id}
              href={`#${section.id}`}
              onClick={(event) => jumpTo(event, section.id)}
              aria-current={isActive ? 'location' : undefined}
              className={cn(
                'focus-visible:ring-ring/50 flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium whitespace-nowrap transition-colors outline-none focus-visible:ring-3',
                isActive
                  ? 'border-transparent bg-primary text-primary-foreground'
                  : 'border-border hover:bg-muted text-muted-foreground hover:text-foreground',
              )}
            >
              <span
                aria-hidden
                className="size-2 shrink-0 rounded-full"
                style={{ backgroundColor: section.color }}
              />
              {section.label}
              <span
                className={cn(
                  'tabular-nums',
                  isActive ? 'text-primary-foreground/70' : 'text-muted-foreground/70',
                )}
              >
                {section.count}
              </span>
            </a>
          )
        })}
      </nav>
    </div>
  )
}

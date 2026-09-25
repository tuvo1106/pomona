import { useState } from 'react'

/** The fade content plays when it replaces its skeleton.
 *
 * A dashboard range change fires ~40 independent queries, and each one's card snapped from
 * grey block to chart the instant it landed. Individually that's a flicker; forty of them
 * arriving over a second or so reads as the page glitching rather than filling in. A short
 * fade turns each arrival into something settling.
 *
 * Short on purpose. These queries are local and usually fast, so a long fade would add more
 * delay than the fetch it's covering, and forty overlapping long fades are their own kind of
 * busy.
 *
 * `motion-safe:` rather than a hook or our own matchMedia: the Tailwind variant compiles to
 * `@media (prefers-reduced-motion: no-preference)`, so a reader who asked for less motion
 * gets the content with no animation and nothing has to re-derive the preference in JS. The
 * charts themselves are recharts' business for the same reason -- see lib/chartStyle.ts,
 * where passing `isAnimationActive` would *replace* the library's own handling of this.
 */
export const CONTENT_FADE_IN =
  'motion-safe:animate-in motion-safe:fade-in motion-safe:duration-200'

/** The fade, but only for content that actually replaced a skeleton.
 *
 * `animate-in` plays on mount, and plenty of mounts aren't loads. The activity card's
 * Rings/Table toggle and the expanded chart's Chart/Table tabs both unmount and remount
 * their content against an already-filled cache, so an unconditional fade would run in
 * response to a direct click -- a loading affordance on an instant interaction, which is
 * the opposite of what it's for. Remembering whether this particular instance ever showed a
 * skeleton keeps it to the transition it was written for.
 */
export function useContentFade(isLoading: boolean): string {
  const [showedSkeleton, setShowedSkeleton] = useState(isLoading)
  // A render-phase update rather than an effect: the class has to be right on the very
  // render that first shows the content, and an effect would land one render too late.
  if (isLoading && !showedSkeleton) setShowedSkeleton(true)
  return showedSkeleton ? CONTENT_FADE_IN : ''
}

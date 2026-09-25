/** The app's mark: one ECG deflection, the same shape the ECG page draws.
 *
 * Inline rather than the `<img src="/favicon.svg">` this replaced. The header's Light / Dark /
 * System toggle is the app's own, and an `<img>` can't see it -- an SVG file that themed
 * itself with `prefers-color-scheme` would go out of step the moment someone picks Light on a
 * dark machine. Here the stroke reads `--group-heart` like every heart chart does, so the mark
 * can never disagree with the surface it's on.
 *
 * public/favicon.svg carries the same path for the tab, where the OS does the theming and a
 * file is the only thing a browser will take. Keep the two in step if the shape changes.
 */
export function AppMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width="20"
      height="20"
      fill="none"
      aria-hidden
      className={className}
    >
      <path
        d="M2 8.5h2.6l1.7-4 2.2 6.6 1.4-2.6H14"
        stroke="var(--group-heart)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

interface Props {
  children: ReactNode
  /** What to show instead of the subtree. Given the error and a reset that re-mounts the
   * subtree, so a card can offer "Try again" without reloading the page.
   */
  fallback: (error: Error, reset: () => void) => ReactNode
  /** Changing this resets the boundary -- pass the route path so navigating away from a
   * broken page doesn't leave the error showing over the new one.
   */
  resetKey?: unknown
}

interface State {
  error: Error | null
  /** The `resetKey` this state was derived against, so a change can be detected during
   * render rather than in a post-update effect.
   */
  resetKey: unknown
}

/** Catches a render error so it takes down one subtree instead of the whole app.
 *
 * A class because there is still no hook for this: `componentDidCatch` has no function
 * equivalent in React 19.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { error: null, resetKey: props.resetKey }
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  /** Clears the error when `resetKey` changes. Done here rather than by setting state in
   * componentDidUpdate, which would render the stale fallback once before replacing it --
   * and, on a route change, flash the previous page's error over the new page.
   */
  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    if (props.resetKey !== state.resetKey) {
      return { error: null, resetKey: props.resetKey }
    }
    return null
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Nowhere to report to -- this app has no server to receive it and no telemetry. The
    // console is the only place a reader (or the developer they file an issue with) can
    // find the stack, so keep it rather than swallowing it.
    console.error('Render error:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return this.props.fallback(this.state.error, () => this.setState({ error: null }))
    }
    return this.props.children
  }
}

/** Whether the page failed because its code never arrived, rather than because it threw
 * while rendering.
 *
 * Matters because the two need different buttons. Re-rendering fixes a transient render
 * error; it cannot fix a failed chunk, because React.lazy caches the rejection and throws
 * the stored error on every subsequent attempt -- "Try again" would look broken. The usual
 * cause is a tab left open across a rebuild, where the chunk it asks for no longer exists,
 * and only a reload picks up the new index.html.
 */
function isChunkLoadError(error: Error): boolean {
  return /dynamically imported module|Importing a module script failed|Loading chunk|ChunkLoadError/i.test(
    `${error.name} ${error.message}`,
  )
}

/** The page-level fallback: something in a whole route failed to render. */
export function PageErrorFallback({ error, reset }: { error: Error; reset: () => void }) {
  const stale = isChunkLoadError(error)
  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="text-foreground text-lg font-semibold">
        {stale ? 'This page needs a reload' : "This page didn't render"}
      </h1>
      <p className="text-muted-foreground mt-2 text-sm">
        {stale
          ? 'The app was rebuilt while this tab was open, so the code for this page is no longer where the tab expects it. Reloading fetches the current version.'
          : 'Something went wrong drawing this page. Your data is untouched — this is a display problem, and the database is only ever read from.'}
      </p>
      <pre className="bg-muted text-muted-foreground mt-4 overflow-x-auto rounded-md p-3 text-xs">
        {error.message}
      </pre>
      {stale ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-4"
          onClick={() => window.location.reload()}
        >
          Reload
        </Button>
      ) : (
        <Button type="button" variant="outline" size="sm" className="mt-4" onClick={reset}>
          Try again
        </Button>
      )}
    </main>
  )
}

/** The card-level fallback: one chart threw, and the other thirty-nine are fine.
 *
 * Deliberately the size of the card it replaces rather than a bare line of text, so the
 * grid doesn't reflow around the gap and send every other card jumping.
 */
export function CardErrorFallback({ title, reset }: { title?: string; reset: () => void }) {
  return (
    <div className="border-border bg-card flex h-[280px] flex-col items-center justify-center gap-2 rounded-xl border p-6 text-center">
      {/* Named, because in a grid of ~40 an anonymous panel doesn't say which metric is
          missing -- and the stack only reaches the console. */}
      <p className="text-muted-foreground text-sm">
        {title ? `${title} couldn't be drawn.` : "This chart couldn't be drawn."}
      </p>
      <Button type="button" variant="ghost" size="sm" onClick={reset}>
        Try again
      </Button>
    </div>
  )
}

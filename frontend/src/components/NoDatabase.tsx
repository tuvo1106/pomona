/** The part of the 503 detail that names the file, without the instruction after it.
 *
 * The server sends one string: "No health database at {path}. Run `pomona ingest
 * <path-to-export.xml>` first." (api/dependencies.py). The command in it is already the
 * <pre> below, so printing the detail whole says it twice -- the second time wrapped in
 * literal backticks, which are markdown the browser doesn't render. The path is the part
 * worth keeping, since it's what reveals a `serve` started from the wrong directory.
 *
 * Falls back to the whole detail if the sentence ever stops looking like this; a slightly
 * redundant line beats an empty one. tests/api/test_dependencies.py pins the prefix.
 */
function databasePath(detail: string): string {
  return detail.split('. Run ')[0]
}

/** Shown in place of every page when the API has no database to read.
 *
 * One full-page state instead of ~40 identical per-card errors: the answer is the same for
 * all of them and it's an instruction, not a fault.
 */
export function NoDatabase({ detail }: { detail: string }) {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="text-foreground text-lg font-semibold">No database yet</h1>
      <p className="text-muted-foreground mt-2 text-sm">
        The server is running, but it has nothing to read. Ingest an export and reload:
      </p>
      <pre className="bg-muted text-foreground mt-4 overflow-x-auto rounded-md p-3 font-mono text-xs">
        pomona ingest &lt;path-to-export.xml&gt;
      </pre>
      <p className="text-muted-foreground mt-4 text-sm">{databasePath(detail)}.</p>
      <p className="text-muted-foreground mt-4 text-xs">
        Already ingested?{' '}
        <code className="bg-muted rounded px-1 py-0.5 font-mono">serve</code> resolves a
        relative database path against the directory you start it from, so running it
        outside the repo root looks exactly like this.
      </p>
    </main>
  )
}

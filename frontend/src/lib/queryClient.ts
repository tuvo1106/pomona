import { QueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/client'

/** Retries worth making. A 4xx won't come good by asking again, and neither will the 503
 * for a missing database -- both need the reader to do something. Everything else (a
 * dropped connection, a server still starting) gets two more tries.
 */
/** `failureCount` is the number of failures *so far*, counted before this call, so
 * `< 2` allows attempts at 0 and 1 -- two retries, three requests in total.
 */
function shouldRetry(failureCount: number, error: Error): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 600) {
    // A 5xx that isn't the no-database 503 falls through to the count below -- the server
    // may still be coming up. The no-database 503 is a settled answer, and so is any 4xx.
    if (error.isNoDatabase || error.status < 500) return false
  }
  return failureCount < 2
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        // The API is this same machine, so react-query's online/offline gating has nothing
        // real to gate on -- and getting it wrong is silent. With the default 'online' mode
        // a failed request whose retry is paused sits at status 'pending', fetchStatus
        // 'paused', error null, forever: `isLoading` is `isPending && isFetching`, so every
        // card reads false/undefined/undefined and renders its *empty* state. A server that
        // is down then looks exactly like an export with no data in it, which for a health
        // dashboard is the worst of the three possible answers. 'always' makes a failure a
        // failure, which the error branches already handle.
        networkMode: 'always',
      },
    },
  })
}

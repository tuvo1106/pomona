import { lazy, Suspense, useEffect, useRef } from 'react'
import { NavLink, Route, Routes, useLocation, useSearchParams } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { AppMark } from '@/components/AppMark'
import { ErrorBoundary, PageErrorFallback } from '@/components/ErrorBoundary'
import { NoDatabase } from '@/components/NoDatabase'
import { PageSkeleton } from '@/components/PageSkeleton'
import { ThemeToggle } from '@/components/ThemeToggle'
import { useDataMeta } from '@/hooks/useAnchoredRange'
import { navSearch } from '@/hooks/useSearchParamState'
import { cn } from '@/lib/utils'

// Split per route. Leaflet and its CSS only matter on /routes, and the ECG page pulls its
// own chart setup -- bundling all four into the entry chunk pushed it past 500 kB, which is
// paid on first paint of the dashboard by everyone who never opens a map.
const DashboardPage = lazy(() =>
  import('@/pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
)
const ClinicalPage = lazy(() =>
  import('@/pages/ClinicalPage').then((m) => ({ default: m.ClinicalPage })),
)
const RoutesPage = lazy(() =>
  import('@/pages/RoutesPage').then((m) => ({ default: m.RoutesPage })),
)
const EcgPage = lazy(() => import('@/pages/EcgPage').then((m) => ({ default: m.EcgPage })))

// Active pages get a filled pill rather than only a color shift: at --muted-foreground vs
// --primary the difference was carried by hue alone, which is the one cue a color-blind or
// low-contrast reader loses. --primary and not the paler --accent: accent sits ~1.09:1 on the
// header and within 2% lightness of the --muted hover fill, so hovering an inactive link
// looked like the active pill and the cue went back to being hue. A filled pill is a
// lightness difference no display setting flattens.
const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'focus-visible:ring-ring/50 rounded-full px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors outline-none focus-visible:ring-3',
    isActive
      ? 'bg-primary text-primary-foreground'
      : 'text-muted-foreground hover:bg-muted hover:text-foreground',
  )

function App() {
  const navRef = useRef<HTMLElement>(null)
  const { pathname, search: currentSearch } = useLocation()
  const [searchParams] = useSearchParams()
  // The range you chose follows you across the nav. Without this, URL state alone would
  // still reset on Dashboard -> Clinical -> Dashboard, which is the thing UI-21 is about:
  // the query would be dropped on the way out. Only the shared keys travel, so a selected
  // ECG recording doesn't follow you to the map (see navSearch).
  const sharedSearch = navSearch(searchParams)
  // ...except for the page you're already on, where the whole query stays. Clicking "ECG"
  // while on /ecg?ecg=12 would otherwise drop the selection and jump the waveform back to
  // the newest recording, which is not what clicking the page you're looking at means.
  const navTo = (to: string) => ({
    pathname: to,
    search: to === pathname ? currentSearch : sharedSearch,
  })
  // Every page's queries already wait on this one (see useAnchoredRange), so it is the
  // first request the app makes and the first to find out there's nothing to read.
  const meta = useDataMeta()
  const noDatabase = meta.error instanceof ApiError && meta.error.isNoDatabase

  // Once the nav scrolls (narrow windows), the current page's pill can sit off the right edge
  // with nothing to say the nav goes on. Pull it into view on navigation. 'nearest' so a nav
  // that isn't scrolling -- the usual case -- doesn't move at all.
  useEffect(() => {
    navRef.current
      ?.querySelector('[aria-current="page"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [pathname])

  return (
    <div className="bg-background text-foreground min-h-screen">
      {/* Translucent rather than bg-inherit: inheriting --background made the sticky header
          opaque, so the backdrop-blur behind it had nothing to blur. The supports- arm keeps
          it nearly solid where backdrop-filter is unavailable, so text stays readable over
          whatever scrolls under it. */}
      <header className="border-border bg-background/90 supports-[backdrop-filter]:bg-background/70 sticky top-0 z-10 flex items-center gap-3 border-b px-4 py-3 backdrop-blur sm:gap-6 sm:px-6">
        <div className="flex shrink-0 items-center gap-2">
          <AppMark className="size-5" />
          <h1 className="text-base font-semibold sm:text-lg">Pomona</h1>
        </div>
        {/* Scrolls sideways below sm instead of wrapping the header onto two rows. The
            negative margins pull back the padding that keeps a focus ring off the overflow
            edges -- on both axes: the ring on the first pill is clipped by the left edge
            otherwise, at every width. */}
        <nav
          ref={navRef}
          className="-mx-1 -my-1 flex min-w-0 flex-1 items-center gap-1 overflow-x-auto p-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          <NavLink to={navTo('/')} end className={navLinkClass}>
            Dashboard
          </NavLink>
          <NavLink to={navTo('/clinical')} className={navLinkClass}>
            Clinical
          </NavLink>
          <NavLink to={navTo('/routes')} className={navLinkClass}>
            Routes
          </NavLink>
          <NavLink to={navTo('/ecg')} className={navLinkClass}>
            ECG
          </NavLink>
        </nav>
        <ThemeToggle />
      </header>

      {/* One answer for the whole app rather than the same 503 rendered into forty cards.
          The nav stays: the pages are all equally empty, but the header is how you know the
          app itself is fine. */}
      {noDatabase ? (
        <NoDatabase detail={meta.error!.message} />
      ) : (
        /* Keyed on the path so navigating away from a page that threw clears the error
           instead of showing it over the page you just moved to. The boundary is outside
           Suspense: a chunk that fails to load rejects, and that should reach the page
           fallback rather than hang on the skeleton forever. */
        <ErrorBoundary
          resetKey={pathname}
          fallback={(error, reset) => <PageErrorFallback error={error} reset={reset} />}
        >
          <Suspense fallback={<PageSkeleton />}>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/clinical" element={<ClinicalPage />} />
              <Route path="/routes" element={<RoutesPage />} />
              <Route path="/ecg" element={<EcgPage />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      )}
    </div>
  )
}

export default App

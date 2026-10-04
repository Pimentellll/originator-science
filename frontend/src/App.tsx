import { useMemo } from 'react'
import { Header } from './components/Header'
import { SummaryBar } from './components/SummaryBar'
import { createTransport } from './lib'
import { BINDER_ROUTES, useRoute } from './state/route'
import { SessionProvider } from './state/session'
import { BenchmarkLab } from './views/BenchmarkLab'
import { Diagnostics } from './views/Diagnostics'
import { Launcher } from './views/Launcher'
import { Cockpit } from './views/Cockpit'
import { ComparePolicies } from './views/ComparePolicies'
import { growthClient } from './views/growth/data'
import { Episode } from './views/growth/Episode'
import { Lab } from './views/growth/Lab'
import { Method } from './views/growth/Method'
import { Results } from './views/growth/Results'
import { Overview } from './views/growth/Overview'

export default function App() {
  const transport = useMemo(() => createTransport(), [])
  const [route, navigate, params] = useRoute()
  return (
    <SessionProvider transport={transport}>
      <div className="app">
        <Header route={route} navigate={navigate} growthKind={growthClient().kind} />
        {BINDER_ROUTES.includes(route) && route !== 'launch' && route !== 'diagnostics' && <SummaryBar />}
        <main className="app__main">
          {route === 'overview' && <Overview navigate={navigate} />}
          {route === 'launch' && <Launcher navigate={navigate} />}
          {route === 'diagnostics' && <Diagnostics />}
          {route === 'results' && <Results navigate={navigate} />}
          {route === 'episode' && <Episode params={params} navigate={navigate} />}
          {route === 'lab' && <Lab />}
          {route === 'method' && <Method />}
          {route === 'cockpit' && <Cockpit navigate={navigate} />}
          {route === 'compare' && <ComparePolicies navigate={navigate} />}
          {route === 'benchmark' && <BenchmarkLab />}
        </main>
      </div>
    </SessionProvider>
  )
}

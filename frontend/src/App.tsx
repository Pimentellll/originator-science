import { useMemo } from 'react'
import { createTransport } from './lib'
import { SessionProvider } from './state/session'
import { useRoute } from './state/route'
import { Header } from './components/Header'
import { Cockpit } from './views/Cockpit'
import { ComparePolicies } from './views/ComparePolicies'
import { BenchmarkLab } from './views/BenchmarkLab'

export default function App() {
  const transport = useMemo(() => createTransport(), [])
  const [route, navigate] = useRoute()
  return (
    <SessionProvider transport={transport}>
      <div className="app">
        <Header route={route} navigate={navigate} />
        <main className="app__main">
          {route === 'cockpit' && <Cockpit navigate={navigate} />}
          {route === 'compare' && <ComparePolicies navigate={navigate} />}
          {route === 'benchmark' && <BenchmarkLab />}
        </main>
      </div>
    </SessionProvider>
  )
}

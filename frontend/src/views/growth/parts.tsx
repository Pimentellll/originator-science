import type { Async } from './data'

export function MetaBar({ items }: { items: [string, string][] }) {
  return (
    <div className="doc__meta">
      <div>
        {items.map(([k, v]) => (
          <span key={k}>
            {k} <b>{v}</b>
          </span>
        ))}
      </div>
    </div>
  )
}

export function DocState<T>({ async, what }: { async: Async<T>; what: string }) {
  return (
    <div className="doc">
      <div className="doc__wrap doc__state">
        {async.state === 'error' ? (
          <>
            <p>Could not load {what}.</p>
            <pre>{async.error}</pre>
            <p>
              Live mode needs the MIRAGE API with <span className="mono">--growth-results</span> and an evaluator token in the dev proxy. Offline, open the app with{' '}
              <span className="mono">?growth=static</span> after <span className="mono">npm run build:static</span>.
            </p>
          </>
        ) : (
          <p>Loading {what}…</p>
        )}
      </div>
    </div>
  )
}

export function Check({ ok, na }: { ok: boolean | null | undefined; na?: string }) {
  if (ok === null || ok === undefined) return <span className="na">{na ?? 'N/A'}</span>
  return ok ? <span className="pass">PASS</span> : <span className="fail">FAIL</span>
}

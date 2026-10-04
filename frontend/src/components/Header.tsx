import { useEffect, useRef, useState } from 'react'
import { useSession } from '../state/sessionContext'
import { BINDER_ROUTES } from '../state/route'
import type { Route } from '../state/route'
import { SECTIONS, TOOLS, sectionOf } from '../state/sections'

function ToolsMenu({ route, navigate }: { route: Route; navigate: (r: Route) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('mousedown', away)
    window.addEventListener('keydown', esc)
    return () => {
      window.removeEventListener('mousedown', away)
      window.removeEventListener('keydown', esc)
    }
  }, [open])
  const active = TOOLS.some((t) => t.id === route)
  return (
    <div className="hdr__tools" ref={ref}>
      <button className="hdr__tab" aria-haspopup="menu" aria-expanded={open} aria-current={active ? 'page' : undefined} onClick={() => setOpen(!open)}>
        Tools ▾
      </button>
      {open && (
        <div className="hdr__menu" role="menu">
          {TOOLS.map((t) => (
            <button
              key={t.id}
              role="menuitem"
              className="hdr__menuitem"
              onClick={() => {
                setOpen(false)
                navigate(t.id)
              }}
            >
              <b>{t.label}</b>
              <span>{t.hint}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function Header({ route, navigate, growthKind }: { route: Route; navigate: (r: Route) => void; growthKind: 'live' | 'static' }) {
  const binder = BINDER_ROUTES.includes(route)
  const session = useSession()
  const transportLabel = session.transport.kind === 'live' ? 'live · MIRAGE API' : session.transport.label.toLowerCase()
  const section = sectionOf(route)
  const current = route === 'episode' ? 'results' : route
  return (
    <>
      <header className="hdr">
        <div className="hdr__brand">
          <button type="button" className="hdr__logo hdr__home" aria-current={route === 'overview' ? 'page' : undefined} title="Overview: what MIRAGE is" onClick={() => navigate('overview')}>
            MIRAG<i>E</i>
          </button>
        </div>
        <nav className="hdr__nav" aria-label="Sections">
          {SECTIONS.map((sec) => (
            <button key={sec.label} className="hdr__tab" title={sec.hint} aria-current={section === sec ? 'page' : undefined} onClick={() => navigate(sec.home)}>
              {sec.label}
            </button>
          ))}
          <ToolsMenu key={route} route={route} navigate={navigate} />
        </nav>
        <div className="hdr__spacer" />
        <span className="hdr__meta mono">{binder ? transportLabel : growthKind === 'static' ? 'offline · static export' : 'live · MIRAGE API'}</span>
      </header>
      {section && section.tabs.length > 0 && (
        <nav className="subnav" aria-label={`${section.label} pages`}>
          <span className="subnav__hint">{section.hint}</span>
          {section.tabs.map((t) => (
            <button key={t.id} className="subnav__tab" aria-current={current === t.id ? 'page' : undefined} onClick={() => navigate(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
      )}
    </>
  )
}

import { describe, expect, it } from 'vitest'
import { parseHash } from './route'

describe('parseHash', () => {
  it('parses routes and their decoded path parameters', () => {
    expect(parseHash('#/episode/RUN/EP')).toEqual({
      route: 'episode',
      params: ['RUN', 'EP'],
    })
  })

  it('defaults unknown routes to the overview', () => {
    expect(parseHash('#/unknown/RUN/EP')).toEqual({ route: 'overview', params: [] })
  })

  it('decodes encoded IDs without splitting their decoded slashes', () => {
    expect(parseHash('#/episode/run%2Fone/ep%20two')).toEqual({
      route: 'episode',
      params: ['run/one', 'ep two'],
    })
  })

  it('ignores a trailing slash', () => {
    expect(parseHash('#/episode/RUN/')).toEqual({ route: 'episode', params: ['RUN'] })
  })

  it('defaults an empty hash to the overview', () => {
    expect(parseHash('')).toEqual({ route: 'overview', params: [] })
    expect(parseHash('#/')).toEqual({ route: 'overview', params: [] })
  })
})

describe('live default', () => {
  it('lands on the launcher for ?transport=live with no hash', () => {
    expect(parseHash('', '?transport=live')).toEqual({ route: 'launch', params: [] })
    expect(parseHash('#/', '?transport=live&seed=4')).toEqual({ route: 'launch', params: [] })
  })
  it('goes straight to the cockpit for a guided link (./mirage demo --guided)', () => {
    expect(parseHash('', '?transport=live&guided=1').route).toBe('cockpit')
  })
  it('keeps an explicit route and the original default otherwise', () => {
    expect(parseHash('#/cockpit', '?transport=live').route).toBe('cockpit')
    expect(parseHash('', '?transport=mock').route).toBe('overview')
  })
})

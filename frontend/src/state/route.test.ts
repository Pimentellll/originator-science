import { describe, expect, it } from 'vitest'
import { parseHash } from './route'

describe('parseHash', () => {
  it('parses routes and their decoded path parameters', () => {
    expect(parseHash('#/episode/RUN/EP')).toEqual({
      route: 'episode',
      params: ['RUN', 'EP'],
    })
  })

  it('defaults unknown routes to results', () => {
    expect(parseHash('#/unknown/RUN/EP')).toEqual({ route: 'results', params: [] })
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

  it('defaults an empty hash to results', () => {
    expect(parseHash('')).toEqual({ route: 'results', params: [] })
    expect(parseHash('#/')).toEqual({ route: 'results', params: [] })
  })
})

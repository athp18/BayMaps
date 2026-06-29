import type { GeocodedPlace, RouteRequest, RouteResponse, TrafficResponse } from '../types'

const BASE = '/api'

const GEOCODE_TTL_MS = 5 * 60 * 1000
const _geocodeCache = new Map<string, { result: GeocodedPlace | null; expires: number }>()

export async function fetchRoute(req: RouteRequest): Promise<RouteResponse> {
  const resp = await fetch(`${BASE}/route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err.detail ?? `Request failed: ${resp.status}`)
  }
  return resp.json()
}

export async function fetchTraffic(): Promise<TrafficResponse> {
  const resp = await fetch(`${BASE}/traffic`)
  if (!resp.ok) throw new Error('Failed to fetch traffic data')
  return resp.json()
}

export async function geocode(query: string): Promise<GeocodedPlace | null> {
  const key = query.trim().toLowerCase()
  const cached = _geocodeCache.get(key)
  if (cached && Date.now() < cached.expires) return cached.result

  const params = new URLSearchParams({
    q: query,
    format: 'json',
    limit: '1',
    // Bias toward Bay Area bounding box
    viewbox: '-123.0,37.0,-121.0,38.4',
    bounded: '1',
  })
  const resp = await fetch(`https://nominatim.openstreetmap.org/search?${params}`, {
    headers: { 'User-Agent': 'bay-area-pathfinder/1.0' },
  })
  if (!resp.ok) return null
  const results = await resp.json()
  const result = results.length
    ? { lat: parseFloat(results[0].lat), lng: parseFloat(results[0].lon), display_name: results[0].display_name }
    : null
  _geocodeCache.set(key, { result, expires: Date.now() + GEOCODE_TTL_MS })
  return result
}

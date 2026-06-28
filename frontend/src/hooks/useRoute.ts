import { useState } from 'react'
import { fetchRoute, geocode } from '../services/api'
import type { Coordinate, RouteResponse } from '../types'

interface UseRouteResult {
  route: RouteResponse | null
  loading: boolean
  error: string | null
  originCoord: Coordinate | null
  destCoord: Coordinate | null
  findRoute: (originQuery: string, destQuery: string) => Promise<void>
}

export function useRoute(): UseRouteResult {
  const [route, setRoute] = useState<RouteResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [originCoord, setOriginCoord] = useState<Coordinate | null>(null)
  const [destCoord, setDestCoord] = useState<Coordinate | null>(null)

  async function findRoute(originQuery: string, destQuery: string) {
    setLoading(true)
    setError(null)
    setRoute(null)

    try {
      const [origin, dest] = await Promise.all([geocode(originQuery), geocode(destQuery)])

      if (!origin) throw new Error(`Could not find location: "${originQuery}"`)
      if (!dest) throw new Error(`Could not find location: "${destQuery}"`)

      setOriginCoord({ lat: origin.lat, lng: origin.lng })
      setDestCoord({ lat: dest.lat, lng: dest.lng })

      const result = await fetchRoute({
        origin_lat: origin.lat,
        origin_lng: origin.lng,
        dest_lat: dest.lat,
        dest_lng: dest.lng,
      })
      setRoute(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  return { route, loading, error, originCoord, destCoord, findRoute }
}

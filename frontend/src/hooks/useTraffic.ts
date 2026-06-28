import { useEffect, useState } from 'react'
import { fetchTraffic } from '../services/api'
import type { TrafficResponse } from '../types'

export function useTraffic() {
  const [traffic, setTraffic] = useState<TrafficResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const data = await fetchTraffic()
        if (!cancelled) setTraffic(data)
      } catch {
        // Traffic is best-effort — silently ignore failures
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    const interval = setInterval(load, 60_000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return { traffic, loading }
}

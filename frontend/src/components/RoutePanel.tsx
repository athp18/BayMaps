import { useState } from 'react'
import type { RouteResponse } from '../types'

interface RoutePanelProps {
  route: RouteResponse | null
  loading: boolean
  error: string | null
}

export function RoutePanel({ route, loading, error }: RoutePanelProps) {
  const [useMiles, setUseMiles] = useState(true)

  if (!loading && !error && !route) return null

  function formatDist(km: number) {
    return useMiles ? `${(km * 0.621371).toFixed(1)} mi` : `${km.toFixed(1)} km`
  }

  function formatStepDist(m: number) {
    return useMiles ? `${(m * 0.000621371).toFixed(2)} mi` : `${(m / 1000).toFixed(2)} km`
  }

  return (
    <div style={styles.panel}>
      {loading && <span style={styles.muted}>Calculating route…</span>}

      {error && <span style={styles.error}>{error}</span>}

      {route && (
        <>
          <div style={styles.row}>
            <Stat label="Distance" value={formatDist(route.distance_km)} />
            <Stat
              label="Duration"
              value={`${route.duration_minutes} min (${route.duration_min_minutes}–${route.duration_max_minutes} min)`}
            />
            {route.traffic_adjusted && (
              <span style={styles.badge}>Traffic-adjusted</span>
            )}
            <button style={styles.toggle} onClick={() => setUseMiles(m => !m)}>
              {useMiles ? 'km' : 'mi'}
            </button>
          </div>
          {route.directions && route.directions.length > 0 && (
            <ol style={styles.directionsList}>
              {route.directions.map((dir, idx) => (
                <li key={idx} style={styles.directionItem}>
                  <span style={styles.directionInstruction}>{dir.instruction}</span>
                  <span style={styles.directionDist}>{formatStepDist(dir.distance_m)}</span>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={styles.label}>{label}</span>
      <span style={styles.value}>{value}</span>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    padding: '10px 16px',
    background: '#f9fafb',
    borderBottom: '1px solid #e5e7eb',
    fontSize: 14,
  },
  row: {
    display: 'flex',
    gap: 24,
    alignItems: 'center',
  },
  label: { fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.5 },
  value: { fontWeight: 600, color: '#111827' },
  muted: { color: '#6b7280' },
  error: { color: '#dc2626' },
  badge: {
    padding: '2px 8px',
    background: '#dbeafe',
    color: '#1d4ed8',
    borderRadius: 12,
    fontSize: 12,
    fontWeight: 500,
  },
  directionsList: {
    margin: '8px 0 0 0',
    padding: '0 0 0 20px',
    maxHeight: 200,
    overflowY: 'auto',
    borderTop: '1px solid #e5e7eb',
    paddingTop: 8,
  },
  directionItem: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '3px 0',
    gap: 12,
  },
  toggle: {
    marginLeft: 'auto',
    padding: '2px 10px',
    fontSize: 12,
    border: '1px solid #d1d5db',
    borderRadius: 12,
    background: '#fff',
    color: '#374151',
    cursor: 'pointer',
  },
  directionInstruction: {
    color: '#374151',
  },
  directionDist: {
    color: '#6b7280',
    whiteSpace: 'nowrap',
    flexShrink: 0,
  },
}

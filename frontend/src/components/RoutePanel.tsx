import type { RouteResponse } from '../types'

interface RoutePanelProps {
  route: RouteResponse | null
  loading: boolean
  error: string | null
}

export function RoutePanel({ route, loading, error }: RoutePanelProps) {
  if (!loading && !error && !route) return null

  return (
    <div style={styles.panel}>
      {loading && <span style={styles.muted}>Calculating route…</span>}

      {error && <span style={styles.error}>{error}</span>}

      {route && (
        <div style={styles.row}>
          <Stat label="Distance" value={`${route.distance_km} km`} />
          <Stat label="Duration" value={`${route.duration_minutes} min`} />
          {route.traffic_adjusted && (
            <span style={styles.badge}>Traffic-adjusted</span>
          )}
        </div>
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
}

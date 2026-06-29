import L from 'leaflet'
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png'
import iconUrl from 'leaflet/dist/images/marker-icon.png'
import shadowUrl from 'leaflet/dist/images/marker-shadow.png'
import { CircleMarker, MapContainer, Polyline, TileLayer } from 'react-leaflet'
import type { Coordinate, RouteResponse } from '../types'

// Fix Leaflet's broken icon paths when bundled with Vite
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl
L.Icon.Default.mergeOptions({ iconRetinaUrl, iconUrl, shadowUrl })


interface MapProps {
  route: RouteResponse | null
  originCoord: Coordinate | null
  destCoord: Coordinate | null
}

export function Map({ route, originCoord, destCoord }: MapProps) {
  const positions = route?.coordinates.map(c => [c.lat, c.lng] as [number, number]) ?? []

  return (
    <MapContainer
      center={[37.7749, -122.4194]}
      zoom={11}
      minZoom={9}
      maxZoom={18}
      maxBounds={[[36.9, -123.0], [38.4, -121.0]]}
      maxBoundsViscosity={1.0}
      style={{ flex: 1, width: '100%' }}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      />

      {positions.length > 0 && (
        <Polyline positions={positions} pathOptions={{ color: '#2563eb', weight: 5, opacity: 0.8 }} />
      )}

      {originCoord && (
        <CircleMarker
          center={[originCoord.lat, originCoord.lng]}
          radius={9}
          pathOptions={{ color: '#16a34a', fillColor: '#16a34a', fillOpacity: 1 }}
        />
      )}

      {destCoord && (
        <CircleMarker
          center={[destCoord.lat, destCoord.lng]}
          radius={9}
          pathOptions={{ color: '#dc2626', fillColor: '#dc2626', fillOpacity: 1 }}
        />
      )}
    </MapContainer>
  )
}

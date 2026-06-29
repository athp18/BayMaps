export interface Coordinate {
  lat: number
  lng: number
}

export interface RouteRequest {
  origin_lat: number
  origin_lng: number
  dest_lat: number
  dest_lng: number
}

export interface Direction {
  instruction: string
  distance_m: number
  street: string
}

export interface RouteResponse {
  coordinates: Coordinate[]
  distance_km: number
  duration_minutes: number
  duration_min_minutes: number
  duration_max_minutes: number
  traffic_adjusted: boolean
  score: number
  directions: Direction[]
}

export interface TrafficSegment {
  lat: number
  lng: number
  congestion_level: number // 0=free, 1=slow, 2=heavy, 3=standstill
}

export interface TrafficResponse {
  segments: TrafficSegment[]
  updated_at: string
}

export interface GeocodedPlace {
  lat: number
  lng: number
  display_name: string
}

from pydantic import BaseModel


class RouteRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float


class Coordinate(BaseModel):
    lat: float
    lng: float


class RouteResponse(BaseModel):
    coordinates: list[Coordinate]
    distance_km: float
    duration_minutes: float
    traffic_adjusted: bool
    score: float


class TrafficSegment(BaseModel):
    lat: float
    lng: float
    congestion_level: int  # 0=free, 1=slow, 2=heavy, 3=standstill


class TrafficResponse(BaseModel):
    segments: list[TrafficSegment]
    updated_at: str

from app.etl.pipeline import has_live_traffic
from app.models.scorer import RouteScorer, extract_route_features

_scorer = RouteScorer()


def predict_route(G, path, cost):
    features = extract_route_features(G, path)
    score = _scorer.score(features)
    return score, has_live_traffic()

"""
Train one XGBoost model per time bucket to predict edge congestion multipliers.

Features per edge:
    lat_mid, lng_mid, osm_speed, length, road_type, degree_u, degree_v,
    bucket_idx, [dist_to_sensor_k, congestion_ratio_k] × 5

Target: congestion multiplier (osm_speed / pems_speed), clipped to [1.0, 4.0]

Output: weights/xgb_<bucket>.json (one per bucket)

Usage:
    cd backend/
    # First build training data (inside Docker):
    #   docker compose run --rm --no-deps backend python -m scripts.build_training_data
    # Then train locally:
    python -m scripts.train_xgb
"""

import logging
import pickle
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TRAINING_DATA_PATH = Path("data/pems/training_data.pkl")
WEIGHTS_DIR = Path("weights")

XGB_PARAMS = {
    "n_estimators": 400,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "reg_lambda": 1.0,
    "objective": "reg:squarederror",
    "tree_method": "hist",
    "n_jobs": -1,
    "random_state": 42,
}

FEATURE_NAMES = [
    "lat_mid", "lng_mid", "osm_speed_norm", "log_length",
    "road_type_norm", "degree_u_norm", "degree_v_norm", "bucket_idx_norm",
    *[f"log_dist_sensor_{k}" for k in range(1, 6)],
    *[f"congestion_ratio_sensor_{k}" for k in range(1, 6)],
]


def train_bucket(bucket, X_labeled, y_labeled):
    X_train, X_test, y_train, y_test = train_test_split(
        X_labeled, y_labeled, test_size=0.2, random_state=42
    )

    model = xgb.XGBRegressor(**XGB_PARAMS)
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    preds = model.predict(X_test)
    mse = mean_squared_error(y_test, preds)
    mae = mean_absolute_error(y_test, preds)
    r2 = r2_score(y_test, preds)
    baseline_mse = mean_squared_error(y_test, np.full_like(preds, y_test.mean()))

    logger.info(
        f"[{bucket}] MSE={mse:.4f}  MAE={mae:.4f}  "
        f"baseline_MSE={baseline_mse:.4f}  R²={r2:.3f}  "
        f"train={len(X_train)}  test={len(X_test)}"
    )

    importances = model.feature_importances_
    top = np.argsort(importances)[::-1][:5]
    logger.info(f"[{bucket}] Top features: {[FEATURE_NAMES[i] for i in top]}")

    return model


def main():
    if not TRAINING_DATA_PATH.exists():
        raise FileNotFoundError(
            f"{TRAINING_DATA_PATH} not found.\n"
            "Run inside Docker first:\n"
            "  docker compose run --rm --no-deps backend python -m scripts.build_training_data"
        )

    with open(TRAINING_DATA_PATH, "rb") as f:
        dataset = pickle.load(f)

    WEIGHTS_DIR.mkdir(exist_ok=True)

    for bucket, data in dataset.items():
        X_labeled = data["X_labeled"]
        y_labeled = data["y_labeled"]
        logger.info(f"\nTraining bucket: {bucket} ({len(y_labeled)} labeled edges)")

        model = train_bucket(bucket, X_labeled, y_labeled)

        out_path = WEIGHTS_DIR / f"xgb_{bucket}.json"
        model.save_model(out_path)
        logger.info(f"Saved: {out_path}")

    logger.info("\nDone. Place weights/xgb_*.json in backend/weights/")


if __name__ == "__main__":
    main()

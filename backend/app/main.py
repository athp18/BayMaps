import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router, init_redis
from app.core.graph import get_graph, load_graph
from app.core.speed_lookup import apply_speed_lookup, load_speed_lookup
from app.etl.pipeline import start_etl_loop
from app.models.xgb_inference import load_models, load_sensor_data, get_multipliers

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    await load_graph()
    G = get_graph()
    load_speed_lookup()
    apply_speed_lookup(G)
    load_models()
    load_sensor_data(G)
    init_redis("redis://redis:6379")

    # Pre-warm XGBoost multiplier cache for the current time bucket
    now = datetime.now()
    hour_of_week = now.weekday() * 24 + now.hour
    logger.info("Pre-warming XGBoost multiplier cache...")
    await asyncio.get_event_loop().run_in_executor(None, get_multipliers, G, hour_of_week)
    logger.info("XGBoost cache warm")

    task = asyncio.create_task(start_etl_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Bay Area Pathfinder", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

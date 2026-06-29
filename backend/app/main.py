import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.graph import get_graph, load_graph
from app.core.speed_lookup import apply_speed_lookup, load_speed_lookup
from app.etl.pipeline import start_etl_loop
from app.models.xgb_inference import load_models, load_sensor_data

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await load_graph()
    G = get_graph()
    load_speed_lookup()
    apply_speed_lookup(G)
    load_models()
    load_sensor_data(G)
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

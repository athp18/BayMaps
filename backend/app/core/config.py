from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_511_key: str = ""
    redis_url: str = "redis://redis:6379"
    graph_path: str = "data/bay_area.graphml"
    etl_interval_seconds: int = 300
    use_demo_graph: bool = True

    model_config = {"env_file": ".env"}


settings = Settings()

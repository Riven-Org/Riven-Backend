import asyncio

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from riven_worker.activities import ALL_ACTIVITIES
from riven_worker.graph_consistency import (
    GraphConsistencyActivities,
    GraphConsistencyWorkflow,
    ensure_nightly_schedule,
)
from riven_worker.workflows import VerificationWorkflow

TASK_QUEUE = "verification"


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RIVEN_", extra="ignore")

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    database_url: str = "postgresql+asyncpg://riven:riven@localhost:5432/riven"


async def main() -> None:
    settings = WorkerSettings()
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        data_converter=pydantic_data_converter,
    )
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    graph = GraphConsistencyActivities(async_sessionmaker(engine, expire_on_commit=False))
    await ensure_nightly_schedule(client, TASK_QUEUE)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[VerificationWorkflow, GraphConsistencyWorkflow],
        activities=[*ALL_ACTIVITIES, graph.check_graph_consistency],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

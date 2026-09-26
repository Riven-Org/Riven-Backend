import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from riven_config import DatabaseSettings, TemporalSettings
from riven_worker.activities import ALL_ACTIVITIES
from riven_worker.graph_consistency import (
    GraphConsistencyActivities,
    GraphConsistencyWorkflow,
    ensure_nightly_schedule,
)
from riven_worker.workflows import VerificationWorkflow

TASK_QUEUE = "verification"


class WorkerSettings(DatabaseSettings, TemporalSettings):
    """Worker settings, validated at startup (ticket S02.2)."""


async def main() -> None:
    settings = WorkerSettings.load()
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        data_converter=pydantic_data_converter,
    )
    engine = create_async_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)
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

import asyncio

from pydantic_settings import BaseSettings, SettingsConfigDict
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from riven_worker.activities import ALL_ACTIVITIES
from riven_worker.workflows import VerificationWorkflow

TASK_QUEUE = "verification"


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RIVEN_", extra="ignore")

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"


async def main() -> None:
    settings = WorkerSettings()
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        data_converter=pydantic_data_converter,
    )
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[VerificationWorkflow],
        activities=ALL_ACTIVITIES,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

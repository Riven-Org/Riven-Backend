from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from botocore.config import Config
from moto import mock_aws

from riven_storage import ObjectStore, StorageSettings, artifact_key


@pytest.fixture
def store() -> Iterator[ObjectStore]:
    with mock_aws():
        settings = StorageSettings(endpoint_url=None, bucket="test-artifacts")
        sigv4 = Config(signature_version="s3v4")
        client = boto3.client("s3", region_name="us-east-1", config=sigv4)
        yield ObjectStore(settings, client)


async def test_artifact_round_trips_through_object_storage(store: ObjectStore) -> None:
    await store.ensure_bucket()
    key = artifact_key("org_a", "run_1", "pytest.log")

    size = await store.put(key, b"1 failed, 3 passed", "text/plain")

    assert size == 18
    assert await store.get(key) == b"1 failed, 3 passed"


async def test_presigned_url_grants_time_limited_download(store: ObjectStore) -> None:
    await store.ensure_bucket()
    key = artifact_key("org_a", "run_1", "junit.xml")
    await store.put(key, b"<testsuite/>", "application/xml")

    url = store.presigned_download_url(key, expires_in=300)

    parsed = urlparse(url)
    assert parsed.path.endswith("/org_a/run_1/junit.xml")
    assert parse_qs(parsed.query)["X-Amz-Expires"] == ["300"]


async def test_ensure_bucket_is_idempotent(store: ObjectStore) -> None:
    await store.ensure_bucket()
    await store.ensure_bucket()


def test_artifact_keys_are_org_prefixed_and_cannot_escape() -> None:
    assert artifact_key("org_a", "run_1", "../../etc/passwd") == "org_a/run_1/.._.._etc_passwd"
    with pytest.raises(ValueError):
        artifact_key("org_a", "..", "log")

"""Opt-in isolated local Docker integration proof; never targets a configured database."""

import asyncio
import hashlib
import json
import os
import secrets
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from cottage_monitoring.api import platform_metrics as pm
from cottage_monitoring.config import settings

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "deploy/platform-metrics"
IMAGE = "sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297"
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("PM_PG_FIXTURE") != "1", reason="explicit isolated Docker opt-in required"
    ),
]


def docker(*args):
    return subprocess.run(
        ["docker", "--context", "desktop-linux", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def make_batch():
    stamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "version": 1,
        "batch_id": str(uuid.uuid4()),
        "producer": "ai-server",
        "created_at": stamp,
        "samples": [
            {
                "service": "gateway",
                "metric": "ready",
                "unit": "bool",
                "observed_at": stamp,
                "status": "observed",
                "value": 1,
            }
        ],
    }


def wire(batch):
    return json.dumps(batch, separators=(",", ":")).encode()


async def wait_db(dsn):
    for _ in range(80):
        try:
            return await asyncpg.connect(dsn, timeout=1)
        except (OSError, asyncpg.PostgresError):
            await asyncio.sleep(0.25)
    raise RuntimeError("isolated PostgreSQL fixture did not start")


async def test_postgres_ingest_and_isolation(monkeypatch, tmp_path):
    name = "pm1-fixture-" + uuid.uuid4().hex[:12]
    password = secrets.token_hex(24)
    writer_password = secrets.token_hex(24)
    envfile = tmp_path / "fixture.env"
    envfile.write_text(
        f"POSTGRES_PASSWORD={password}\nPOSTGRES_USER=fixture_admin\nPOSTGRES_DB=fixture\n"
    )
    envfile.chmod(0o600)
    started = False
    admin = None
    try:
        # Explicit --pull=never, random loopback port and no bind mounts or named volumes.
        docker(
            "run",
            "--detach",
            "--pull=never",
            "--name",
            name,
            "--cpus=1",
            "--memory=384m",
            "--env-file",
            str(envfile),
            "-p",
            "127.0.0.1::5432",
            IMAGE,
        )
        started = True
        port = docker("port", name, "5432/tcp").rsplit(":", 1)[1]
        admin = await wait_db(f"postgresql://fixture_admin:{password}@127.0.0.1:{port}/fixture")
        await admin.execute(
            "CREATE ROLE platform_metrics_owner NOLOGIN; "
            "CREATE ROLE platform_metrics_reader NOLOGIN; "
            "CREATE ROLE platform_metrics_maintenance LOGIN; "
            "CREATE ROLE platform_metrics_writer LOGIN PASSWORD '" + writer_password + "';"
        )
        await admin.execute("CREATE TABLE public.household_secret (value text)")
        await admin.execute((SQL / "001_schema.sql").read_text())
        await admin.execute((SQL / "002_grants.sql").read_text())
        writer_url = f"postgresql+asyncpg://platform_metrics_writer:{writer_password}@127.0.0.1:{port}/fixture"
        monkeypatch.setattr(settings, "platform_metrics_db_url", writer_url)
        monkeypatch.setattr(pm, "_engine", None)
        monkeypatch.setattr(pm, "_engine_dsn", None)
        monkeypatch.setattr(pm, "_tokens", 10.0)
        token = tmp_path / "token"
        token.write_text("fixture-token")
        token.chmod(0o600)
        monkeypatch.setattr(settings, "platform_metrics_enabled", True)
        monkeypatch.setattr(settings, "platform_metrics_token_file", str(token))
        app = FastAPI()
        app.include_router(pm.router, prefix="/api/v1")
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://fixture"
        )
        async with client:
            batch = make_batch()
            body = wire(batch)
            headers = {"Authorization": "Bearer fixture-token", "Content-Type": "application/json"}
            first = await client.post(
                "/api/v1/platform-metrics/batches", content=body, headers=headers
            )
            again = await client.post(
                "/api/v1/platform-metrics/batches", content=body, headers=headers
            )
            assert first.status_code == 200 and first.json()["result"] == "accepted"
            assert again.status_code == 200 and again.json()["result"] == "duplicate"
            altered = dict(batch)
            altered["samples"] = [dict(batch["samples"][0], value=0)]
            conflict = await client.post(
                "/api/v1/platform-metrics/batches", content=wire(altered), headers=headers
            )
            assert conflict.status_code == 409
            assert await admin.fetchval("SELECT count(*) FROM platform_metrics.batches") == 1
            assert await admin.fetchval("SELECT count(*) FROM platform_metrics.samples") == 1
            concurrent = make_batch()
            raw = wire(concurrent)
            results = await asyncio.gather(
                *[pm.store(concurrent, hashlib.sha256(raw).digest()) for _ in range(2)]
            )
            assert sorted(results) == ["accepted", "duplicate"]
            assert await admin.fetchval("SELECT count(*) FROM platform_metrics.samples") == 2
            # Reject only the second insert: first batch insert must roll back atomically.
            await admin.execute(
                "ALTER TABLE platform_metrics.samples ADD CONSTRAINT fixture_reject "
                "CHECK (service <> 'qwen')"
            )
            rejected = make_batch()
            rejected["samples"][0]["service"] = "qwen"
            response = await client.post(
                "/api/v1/platform-metrics/batches", content=wire(rejected), headers=headers
            )
            assert response.status_code == 503
            assert (
                await admin.fetchval(
                    "SELECT count(*) FROM platform_metrics.batches WHERE batch_id=$1",
                    uuid.UUID(rejected["batch_id"]),
                )
                == 0
            )
            await admin.execute(
                "ALTER TABLE platform_metrics.samples DROP CONSTRAINT fixture_reject"
            )
        writer = await asyncpg.connect(
            f"postgresql://platform_metrics_writer:{writer_password}@127.0.0.1:{port}/fixture"
        )
        try:
            for statement in (
                "CREATE TABLE platform_metrics.forbidden (x int)",
                "DELETE FROM platform_metrics.batches",
                "INSERT INTO public.household_secret VALUES ('x')",
            ):
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    await writer.execute(statement)
        finally:
            await writer.close()
        # Aged fixture batch is removed with its samples; current and household rows remain.
        await admin.execute("INSERT INTO public.household_secret VALUES ('preserve')")
        await admin.execute(
            "UPDATE platform_metrics.batches SET received_at=now()-interval '31 days' "
            "WHERE batch_id=$1",
            uuid.UUID(batch["batch_id"]),
        )
        await admin.execute("SET ROLE platform_metrics_maintenance")
        await admin.execute((SQL / "cleanup.sql").read_text())
        await admin.execute("RESET ROLE")
        assert await admin.fetchval("SELECT count(*) FROM platform_metrics.batches") == 1
        assert await admin.fetchval("SELECT count(*) FROM platform_metrics.samples") == 1
        assert await admin.fetchval("SELECT count(*) FROM public.household_secret") == 1
        await pm._engine.dispose()
        monkeypatch.setattr(pm, "_engine", None)
        await admin.execute((SQL / "rollback.sql").read_text())
        assert await admin.fetchval("SELECT to_regnamespace('platform_metrics') IS NULL")
        assert await admin.fetchval("SELECT count(*) FROM public.household_secret") == 1
    finally:
        if pm._engine is not None:
            await pm._engine.dispose()
        if admin is not None:
            await admin.close()
        envfile.unlink(missing_ok=True)
        (tmp_path / "token").unlink(missing_ok=True)
        if started:
            docker("rm", "--force", "--volumes", name)
            assert (
                subprocess.run(
                    ["docker", "--context", "desktop-linux", "inspect", name], capture_output=True
                ).returncode
                != 0
            )

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from src.app import app, service
from src.service import BacktestService


def test_period_endpoint_validates_dates_and_passes_user():
    with patch.object(service, 'delete_runs_in_period', new_callable=AsyncMock) as delete:
        delete.return_value = 3
        client = TestClient(app)
        params = {'date_from': '2026-09-01T00:00:00+04:00', 'date_to': '2026-09-02T00:00:00+04:00'}
        response = client.delete('/backtests', params=params, headers={'x-user-id': 'test-user'})
        assert response.status_code == 200
        assert response.json() == {'deleted_count': 3}
        assert delete.call_args.args[0] == 'test-user'
        delete.reset_mock()
        for invalid in ({}, {**params, 'date_to': params['date_from']},
                        {**params, 'date_from': '2026-09-03T00:00:00Z'},
                        {**params, 'date_from': '2026-09-01T00:00:00'}):
            assert client.delete('/backtests', params=invalid).status_code == 422
        delete.assert_not_called()


@pytest.mark.skipif(not os.environ.get('DATABASE_URL'), reason='Requires PostgreSQL')
def test_period_deletion_boundaries_and_isolation():
    async def check():
        connection = await asyncpg.connect(os.environ['DATABASE_URL'])
        transaction = connection.transaction()
        await transaction.start()
        try:
            user = str(uuid4())
            start = datetime(2026, 9, 1, tzinfo=timezone.utc)
            end = start + timedelta(days=1)
            cases = [
                (user, 'COMPLETED', start, True),
                (user, 'FAILED', end - timedelta(microseconds=1), True),
                (user, 'CANCELLED', start, True),
                (user, 'COMPLETED', start - timedelta(microseconds=1), False),
                (user, 'COMPLETED', end, False),
                (user, 'RUNNING', start, False),
                (user, 'QUEUED', start, False),
                (str(uuid4()), 'COMPLETED', start, False),
            ]
            ids = []
            for owner, status, created, _ in cases:
                identifier = uuid4()
                ids.append(identifier)
                await connection.execute("""INSERT INTO backtest_runs
                    (id,user_id,symbol,timeframe,status,request,created_at)
                    VALUES($1,$2,'TEST','M1',$3,'{}'::jsonb,$4)""", identifier, owner, status, created)

            class Pool:
                @asynccontextmanager
                async def acquire(self):
                    yield connection

            instance = BacktestService.__new__(BacktestService)
            instance.db = Pool()
            assert await instance.delete_runs_in_period(user, start, end) == 3
            remaining = set(await connection.fetch("SELECT id FROM backtest_runs WHERE id=ANY($1::uuid[])", ids))
            assert {row['id'] for row in remaining} == {identifier for identifier, case in zip(ids, cases) if not case[3]}
            assert await instance.delete_runs_in_period(user, start, end) == 0
        finally:
            await transaction.rollback()
            await connection.close()
    asyncio.run(check())

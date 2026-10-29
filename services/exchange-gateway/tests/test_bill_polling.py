import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from urllib.parse import parse_qs,urlsplit

import pytest

from src.service import ExchangeGateway


def gateway():
    item=ExchangeGateway(SimpleNamespace(history_concurrency=1,okx_demo=False))
    item.db=AsyncMock();item.db.fetchrow.return_value=None
    item.require_safe_account_config=AsyncMock(return_value={'uid':'account'})
    item.flush_exchange_event_outbox=AsyncMock();item.enqueue_exchange_event=AsyncMock()
    return item


def test_empty_bill_window_advances_cursor_after_complete_scan():
    async def check():
        item=gateway();item.private=AsyncMock(return_value=[])
        await item.sync_account_bills()
        params=parse_qs(urlsplit(item.private.await_args.args[1]).query)
        assert item.db.execute.await_args.args[1:] == ('PRODUCTION:account',int(params['end'][0]))
    asyncio.run(check())


def test_bill_pagination_uses_stable_window_and_older_bill_cursor():
    async def check():
        item=gateway();page=[{'billId':str(i),'type':'1','ts':'1000'} for i in range(100)]
        item.private=AsyncMock(side_effect=[page,[]])
        with patch('src.service.asyncio.sleep',new=AsyncMock()):
            await item.sync_account_bills()
        params=[parse_qs(urlsplit(call.args[1]).query) for call in item.private.await_args_list]
        assert params[1]['after']==['99']
        for key in ['begin','end','ccy','instType']:assert params[0][key]==params[1][key]
        assert params[0]['ccy']==['USDT'] and params[0]['instType']==['SWAP']
    asyncio.run(check())


def test_failed_second_page_does_not_advance_durable_cursor():
    async def check():
        item=gateway();page=[{'billId':str(i),'type':'1','ts':'1000'} for i in range(100)]
        item.private=AsyncMock(side_effect=[page,ConnectionError('exchange unavailable')])
        with patch('src.service.asyncio.sleep',new=AsyncMock()):
            with pytest.raises(ConnectionError):await item.sync_account_bills()
        item.db.execute.assert_not_awaited()
    asyncio.run(check())


def test_bills_without_stable_account_identity_are_never_imported():
    async def check():
        item=gateway();item.require_safe_account_config.return_value={};item.private=AsyncMock()
        with pytest.raises(ValueError,match='UID'):await item.sync_account_bills()
        item.private.assert_not_awaited()
    asyncio.run(check())

@pytest.mark.parametrize('bill',[
    {'billId':'funding','subType':'173','pnl':'-0.5','ts':'1000'},
    {'billId':'unknown-order','type':'2','ordId':'unowned','fee':'-0.1','ts':'1000'},
])
def test_funding_and_unknown_order_bills_preserve_missing_contract_size(bill):
    class Connection:
        async def __aenter__(self):return self
        async def __aexit__(self,*_):return False
        def transaction(self):return self
    async def check():
        item=gateway();item.db.acquire=lambda:Connection()
        item.private=AsyncMock(return_value=[bill])
        await item.sync_account_bills()
        payload=item.enqueue_exchange_event.await_args.args[1]['payload']
        assert payload['contract_value'] is None
        assert payload['account_scope']=='PRODUCTION:account'
        assert payload['local_order_id'] is None
    asyncio.run(check())

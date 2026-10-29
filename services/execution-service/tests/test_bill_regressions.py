"""Stateful regressions for actual exchange costs; no database or exchange access."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from src.models import Position
from src.service import ExecutionService


class BillStore:
    def __init__(self):
        self.position=Position(id='position',order_id='entry',symbol='AVAX-USDT-SWAP',direction='LONG',
            entry_price=100,current_price=101,quantity=0,initial_quantity=10,leverage=2,
            execution_mode='PRODUCTION',account_scope='PRODUCTION:uid',status='CLOSED',
            activation_id='activation',initial_stop_loss_price=95,entry_fee_percent=.01,
            taker_fee_percent=.01,fees=.2,realized_pnl=9.8).model_dump()
        self.trade={'pnl':9.8,'fees':.2,'funding':0,'pnl_percent':1.96,'r_multiple':.196}
        self.applied=set()
        self.fetch=AsyncMock(side_effect=self._fetch)
        self.fetchrow=AsyncMock(side_effect=self._fetchrow)
        self.fetchval=AsyncMock(side_effect=self._fetchval)
        self.execute=AsyncMock(side_effect=self._execute)
    def acquire(self):return self
    def transaction(self):return self
    async def __aenter__(self):return self
    async def __aexit__(self,*_):return False
    async def _fetch(self,query,*args):
        if 'FROM positions' in query:return [{'id':'position','data':dict(self.position)}]
        return []
    async def _fetchrow(self,query,*args):
        if 'FROM positions' in query:return {'data':dict(self.position)}
        if 'FROM closed_trades' in query:return {'data':dict(self.trade)}
        if 'FROM trading_configs' in query:return None
        raise AssertionError(query)
    async def _fetchval(self,query,*args):
        if 'INSERT INTO exchange_account_bills' in query:
            identity=args[:2]
            if identity in self.applied:return None
            self.applied.add(identity);return args[1]
        raise AssertionError(query)
    async def _execute(self,query,*args):
        if query.startswith('UPDATE positions SET data='):self.position=json.loads(args[1])
        elif query.startswith('UPDATE closed_trades SET pnl='):self.trade=json.loads(args[2])
        else:raise AssertionError(query)


@pytest.mark.parametrize('bill,expected_pnl,expected_fees,expected_funding',[
    ({'type':'2','ordId':'exchange-entry','sz':'10','px':'100','fee':'-0.15'},9.75,.25,0),
    ({'type':'2','ordId':'exchange-entry','sz':'10','px':'100','fee':'0.05'},9.95,.05,0),
    ({'type':'8','subType':'173','ts':'1000','pnl':'-0.4'},9.4,.2,.4),
    ({'type':'8','subType':'174','ts':'1000','pnl':'0.3'},10.1,.2,-.3),
])
def test_actual_costs_correct_closed_trade_once_and_refresh_cached_position(bill,expected_pnl,expected_fees,expected_funding):
    async def check():
        store=BillStore();service=ExecutionService('unused','unused');service.db=store
        service.positions['position']=Position.model_validate(store.position)
        payload={'account_scope':'PRODUCTION:uid','execution_mode':'PRODUCTION',
                 'local_order_id':'entry','contract_value':1,'bill':{'billId':'bill', 'instId':'AVAX-USDT-SWAP',**bill}}
        assert await service.apply_exchange_bill(payload)
        assert not await service.apply_exchange_bill(payload)
        assert store.trade['pnl']==pytest.approx(expected_pnl)
        assert store.trade['fees']==pytest.approx(expected_fees)
        assert store.trade['funding']==pytest.approx(expected_funding)
        assert store.trade['pnl_percent']==pytest.approx(expected_pnl/500*100)
        assert store.trade['r_multiple']==pytest.approx(expected_pnl/50)
        assert service.positions['position'].realized_pnl==pytest.approx(expected_pnl)
        assert len(store.applied)==1
    asyncio.run(check())


def test_bill_correction_preserves_newer_protection_state_from_locked_row():
    async def check():
        store=BillStore();stale=dict(store.position)
        store.position['protected']=True;store.position['stop_loss_price']=100
        async def stale_read(*_):return [{'id':'position','data':dict(stale)}]
        store.fetch.side_effect=stale_read
        service=ExecutionService('unused','unused');service.db=store
        await service.apply_exchange_bill({'account_scope':'PRODUCTION:uid','execution_mode':'PRODUCTION',
            'local_order_id':'entry','contract_value':1,'bill':{'billId':'fee','type':'2',
                'ordId':'exchange-entry','sz':'10','px':'100','fee':'-0.15'}})
        assert store.position['protected'] is True and store.position['stop_loss_price']==100
        assert store.position['realized_pnl']==pytest.approx(9.75)
    asyncio.run(check())


def test_funding_before_close_is_included_in_final_capital_exactly_once():
    async def check():
        store=BillStore();store.position.update(status='OPENED',quantity=10,fees=0,realized_pnl=0)
        store.trade=None
        original_row=store._fetchrow;original_value=store._fetchval;original_execute=store._execute
        async def row(query,*args):
            if 'FROM closed_trades' in query and store.trade is None:return None
            return await original_row(query,*args)
        async def value(query,*args):
            if query.startswith('SELECT id FROM positions'):return 'position'
            if 'INSERT INTO closed_trades' in query:
                store.trade=json.loads(args[3]);return 'position'
            return await original_value(query,*args)
        async def execute(query,*args):
            if query.startswith("UPDATE positions SET status='CLOSED'"):
                store.position=json.loads(args[1]);return
            if 'position_state_history' in query or 'execution_outbox' in query:return
            return await original_execute(query,*args)
        store.fetchrow.side_effect=row;store.fetchval.side_effect=value;store.execute.side_effect=execute
        service=ExecutionService('unused','unused');service.db=store;service.redis=AsyncMock()
        p=Position.model_validate(store.position);service.positions[p.id]=p
        service.update_current_capital=AsyncMock(return_value=[]);service.flush_outbox=AsyncMock()
        await service.apply_exchange_bill({'account_scope':'PRODUCTION:uid','execution_mode':'PRODUCTION',
            'bill':{'billId':'funding','subType':'173','ts':p.opened_at+1,'instId':p.symbol,'pnl':'-0.4'}})
        assert p.realized_pnl==pytest.approx(-.4)
        await service.close(p,10,101,'MANUAL',exchange_fill=True)
        assert p.realized_pnl==pytest.approx(9.399)
        assert store.trade['funding']==pytest.approx(.4)
        assert service.update_current_capital.await_args.args[1]==pytest.approx(9.399)
    asyncio.run(check())

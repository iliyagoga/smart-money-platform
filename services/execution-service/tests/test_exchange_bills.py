import asyncio
import json
from unittest.mock import AsyncMock

from src.models import Position
from src.service import ExecutionService


class Tx:
    async def __aenter__(self):return self
    async def __aexit__(self,*_):return False


class OpenFundingStore:
    def __init__(self,position):
        self.position=position
        self.applied=set()
        self.db=self
    def acquire(self):return self
    def transaction(self):return Tx()
    async def __aenter__(self):return self
    async def __aexit__(self,*_):return False
    async def fetch(self,query,*args):return [{"id":self.position["id"],"data":dict(self.position)}]
    async def fetchrow(self,query,*args):
        if "FROM positions" in query:return {"data":dict(self.position)}
        return None
    async def fetchval(self,query,*args):
        key=args[:2]
        if key in self.applied:return None
        self.applied.add(key);return args[1]
    async def execute(self,query,*args):
        if query.startswith("UPDATE positions SET data="):self.position=json.loads(args[1])


def test_unmatched_exchange_bill_is_durably_pending_and_scoped():
    async def check():
        service=ExecutionService("postgres://unused","redis://unused")
        service.db=AsyncMock()
        service.db.fetch.return_value=[]
        service.db.fetchrow.return_value=None
        payload={"account_scope":"PRODUCTION:uid-1","execution_mode":"PRODUCTION",
                 "local_order_id":None,"bill":{"billId":"b-1","ordId":"ex-1","type":"2","fee":"-0.1"}}
        assert not await service.apply_exchange_bill(payload)
        service.db.execute.assert_awaited_once()
        args=service.db.execute.await_args.args
        assert "ON CONFLICT(account_scope,bill_id) DO UPDATE" in args[0]
        assert args[1:3]==("PRODUCTION:uid-1","b-1")
    asyncio.run(check())


def test_reduce_only_bill_resolves_position_through_exit_order_reference():
    async def check():
        service=ExecutionService("postgres://unused","redis://unused")
        service.db=AsyncMock()
        position_id="00000000-0000-0000-0000-000000000011"
        service.db.fetch.return_value=[{"id":position_id,"data":{
          "status":"OPEN","account_scope":"DEMO:uid-2","order_id":"entry-order",
          "execution_mode":"DEMO"}}]
        payload={"account_scope":"DEMO:uid-2","execution_mode":"DEMO",
          "local_order_id":"exit-order","is_exit_order":True,"contract_value":.01,
          "bill":{"billId":"b-exit","ordId":"exchange-exit","type":"2","fee":"-0.02"}}
        assert not await service.apply_exchange_bill(payload)
        query=service.db.fetch.await_args.args[0]
        assert "LEFT JOIN orders o ON o.id=$1::uuid" in query
        args=service.db.execute.await_args.args
        assert args[1]=="DEMO:uid-2" and args[2]=="b-exit"
        assert args[4]==position_id
    asyncio.run(check())


def test_open_funding_is_applied_once_and_kept_for_later_close():
    async def check():
        position={"id":"00000000-0000-0000-0000-000000000021","order_id":"entry",
          "symbol":"AVAX-USDT-SWAP","direction":"LONG","execution_mode":"DEMO",
          "account_scope":"DEMO:uid-2","status":"OPEN","entry_price":100,
          "current_price":101,"quantity":1,"initial_quantity":1,"realized_pnl":0,
          "fees":.1,"funding":0,"actual_funding_adjustment":0}
        store=OpenFundingStore(position)
        service=ExecutionService("unused","unused");service.db=store
        service.positions[position["id"]]=Position.model_validate(position)
        payload={"account_scope":"DEMO:uid-2","execution_mode":"DEMO","local_order_id":None,
          "bill":{"billId":"fund-1","instId":"AVAX-USDT-SWAP","type":"8","subType":"173",
                  "ts":"1000","pnl":"-0.25"}}
        assert await service.apply_exchange_bill(payload)
        assert not await service.apply_exchange_bill(payload)
        cached=service.positions[position["id"]]
        assert cached.realized_pnl==-.25 and cached.funding==.25
        assert store.position["realized_pnl"]==-.25 and store.position["funding"]==.25
    asyncio.run(check())


def test_pending_child_fee_re_resolves_from_persisted_bill_after_mapping_arrives():
    async def check():
        service=ExecutionService("unused","unused")
        service.db=AsyncMock()
        service.db.fetchrow.return_value={"local_order_id":"00000000-0000-0000-0000-000000000031",
          "contract_value":.01,"is_exit":True}
        service.db.fetch.return_value=[]
        payload={"account_scope":"PRODUCTION:uid-3","execution_mode":"PRODUCTION",
          "local_order_id":None,"contract_value":None,
          "bill":{"billId":"late-child-fee","ordId":"child-exchange-id","type":"2","fee":"-0.01"}}
        assert not await service.apply_exchange_bill(payload)
        query=service.db.fetchrow.await_args.args[0]
        assert "jsonb_each_text(eo.exit_order_ids)" in query
        saved=json.loads(service.db.execute.await_args.args[3])
        assert saved["local_order_id"]=="00000000-0000-0000-0000-000000000031"
        assert saved["contract_value"]==.01 and saved["is_exit_order"] is True
    asyncio.run(check())


def test_generated_reduce_only_order_keeps_parent_account_and_activation_scope():
    async def check():
        service=ExecutionService("unused","unused")
        service.save_order=AsyncMock();service.stream=AsyncMock()
        parent=Position(order_id="entry",symbol="AVAX-USDT-SWAP",direction="LONG",entry_price=100,
          current_price=99,quantity=1,initial_quantity=1,execution_mode="DEMO",
          account_scope="DEMO:uid-4",activation_id="activation-4")
        order=await service.request_position_close(parent,1,"MANUAL")
        assert order.reduce_only and order.position_id==parent.id
        assert order.account_scope==parent.account_scope and order.activation_id==parent.activation_id
    asyncio.run(check())

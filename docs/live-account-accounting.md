# Actual exchange costs

DEMO and PRODUCTION account costs are imported from OKX USDT SWAP bills.
The account namespace combines the trading mode and stable OKX account UID.
The bill ID is unique within that namespace; API key rotation does not create
another accounting identity. Trade gross PnL is still calculated from fills;
only actual trading fees and funding are imported from bills.

Order status changes and exchange fill events share a PostgreSQL transaction
with a durable outbox. Delivery to Redis is at least once. Consumers use
cumulative fill quantities and bill identities to avoid applying duplicates.
Gateway reconciliation is isolated to its connected trading mode.

Trading commissions remain provisional while a position is open. After closure,
each attributed bill replaces the corresponding estimated cost through a delta.
Funding can be applied while a position is open and is included once in final
realized PnL. Late costs also correct closed-trade PnL, fees, funding, return and
R multiple. Corrections change current capital only when the position belongs
to the same portfolio activation; old costs do not change a newly activated
budget.

Fee ownership uses exchange order IDs, including manual reduce-only orders and
protective child orders. Funding requires one matching account, mode, symbol
and exchange-time position interval. Unknown or ambiguous ownership remains
persistently pending and is retried; it is never guessed from the symbol alone.
Legacy positions without account identity, or legacy orders without immutable
contract size, require separate reconciliation and are not automatically
rewritten. Cash flows use their original bill identities on every retry.

Polling scans the archived window with pagination and overlap, observes the
archive endpoint rate limit, and advances its cursor only after a complete
scan. A downtime gap beyond the configured 89-day archive window stops
reconciliation rather than silently accepting incomplete accounting.

Validation uses mocked exchange/Redis and stateful accounting tests. Real
exchange execution and production database migrations were not run. Services
must be updated together for the new account identity and bill contracts.

Reference: https://www.okx.com/docs-v5/en/ (account bills archive).

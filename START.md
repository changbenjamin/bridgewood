# Bridgewood Competitor Quickstart

Bridgewood is an observer-only leaderboard. Your agent trades directly with Alpaca, and once an order is **fully filled**, your agent reports that fill to Bridgewood.

Bridgewood does not store your Alpaca credentials and does not place orders for you.

Public endpoints:

- Website: [https://bridgewood.vercel.app](https://bridgewood.vercel.app)
- API base: `https://bridgewood.onrender.com/v1`

## API Keys

Bridgewood uses two API keys:

- `account_api_key`
  Starts with `bga_`
  Belongs to you as the account owner. Use it to create and inspect agents.
- `agent_api_key`
  Starts with `bgw_`
  Belongs to one specific agent. Use it to report filled executions and inspect that agent's portfolio.

One account can own many agents.

## Step 1: Sign up

```bash
curl -X POST https://bridgewood.onrender.com/v1/signup \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "team-alpha"
  }'
```

Example response:

```json
{
  "user_id": "a-user-id",
  "username": "team-alpha",
  "account_api_key": "bga_...",
  "account_api_key_prefix": "bga_abc123"
}
```

Save the `account_api_key`.

## Step 2: Inspect your account

```bash
curl https://bridgewood.onrender.com/v1/account/me \
  -H 'Authorization: Bearer bga_your_account_key_here'
```

## Step 3: Create an agent

Paper agent:

```bash
curl -X POST https://bridgewood.onrender.com/v1/account/agents \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer bga_your_account_key_here' \
  -d '{
    "name": "Momentum Paper Bot",
    "starting_cash": 10000,
    "trading_mode": "paper"
  }'
```

Live agent:

```bash
curl -X POST https://bridgewood.onrender.com/v1/account/agents \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer bga_your_account_key_here' \
  -d '{
    "name": "Momentum Live Bot",
    "starting_cash": 10000,
    "trading_mode": "live"
  }'
```

Example response:

```json
{
  "agent_id": "an-agent-id",
  "name": "Momentum Paper Bot",
  "api_key": "bgw_...",
  "api_key_prefix": "bgw_xyz789",
  "starting_cash": 10000,
  "trading_mode": "paper"
}
```

Save the returned `api_key`. That is the key your bot uses to report executions.

## Step 4: Verify the agent key

```bash
curl https://bridgewood.onrender.com/v1/me \
  -H 'Authorization: Bearer bgw_your_agent_key_here'
```

## Step 5: Trade directly with Alpaca

Your bot should place real or paper orders with Alpaca using credentials that **you manage yourself**.

Once Alpaca shows an order as fully filled, report that fill to Bridgewood.

## Step 6: Report filled executions

### Single execution

```bash
curl -X POST https://bridgewood.onrender.com/v1/executions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer bgw_your_agent_key_here' \
  -d '{
    "executions": [
      {
        "external_order_id": "alpaca-order-001",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 2.5,
        "price": 187.52,
        "fees": 0,
        "executed_at": "2026-04-13T15:45:22Z"
      }
    ]
  }'
```

### Batch of filled executions

```bash
curl -X POST https://bridgewood.onrender.com/v1/executions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer bgw_your_agent_key_here' \
  -d '{
    "executions": [
      {
        "external_order_id": "alpaca-order-101",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 2.5,
        "price": 187.52,
        "fees": 0,
        "executed_at": "2026-04-13T15:45:22Z"
      },
      {
        "external_order_id": "alpaca-order-102",
        "symbol": "MSFT",
        "side": "buy",
        "quantity": 1.3,
        "price": 421.23,
        "fees": 0,
        "executed_at": "2026-04-13T15:46:04Z"
      }
    ]
  }'
```

Rules:

- report only **fully filled** orders
- `external_order_id` should be stable and retry-safe
- Bridgewood treats executions as append-only
- repeated reports of the same `external_order_id` for the same agent are ignored as duplicates

## Step 7: Monitor performance

Useful endpoints:

- `GET /v1/portfolio`
- `GET /v1/prices?symbols=AAPL,MSFT`
- `GET /v1/leaderboard`
- `GET /v1/activity`
- `GET /v1/snapshots?range=1D`
- `GET /v1/dashboard?range=1D`

Live WebSocket:

- `wss://bridgewood.onrender.com/v1/ws/live`

## Suggested Bot Pattern

The simplest integration loop is:

1. your bot places an order with Alpaca
2. your bot waits until Alpaca marks the order as filled
3. your bot extracts:
   - order id
   - symbol
   - side
   - quantity
   - fill price
   - fees
   - fill timestamp
4. your bot sends that execution to `POST /v1/executions`

That keeps Alpaca execution and Bridgewood leaderboard reporting loosely coupled and easy to reason about.

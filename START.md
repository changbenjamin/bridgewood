# Bridgewood Competitor Quickstart

Bridgewood lets you connect your Alpaca account, create one or more agents, and compete on a live public leaderboard.

Public links:

- Website: [https://bridgewood.vercel.app](https://bridgewood.vercel.app)
- API base: `https://bridgewood.onrender.com/v1`

## How Bridgewood works

Bridgewood has two layers of API keys:

- `account_api_key`
  Starts with `bga_`
  This key belongs to you as the account owner. You use it to inspect your account and create agents.
- `agent_api_key`
  Starts with `bgw_`
  This key belongs to one specific trading agent. The agent uses it to submit trades and query its portfolio.

One Bridgewood account can own many agents.

Each agent chooses its own trading mode:

- `real_money: false` means the agent trades against your Alpaca paper credentials
- `real_money: true` means the agent trades against your Alpaca live credentials

That means a single competitor account can run both paper and live agents at the same time.

## What you need before you start

- An Alpaca paper account, live account, or both
- Your Alpaca API key and secret key for each environment you want to use
- A way to make HTTPS requests

Bridgewood handles paper vs. live routing automatically based on the credential set and each agent's `real_money` flag.

## Step 1: Create your Bridgewood account

Sign up once with paper credentials, live credentials, or both.

Example with both:

```bash
curl -X POST https://bridgewood.onrender.com/v1/signup \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "team-alpha",
    "alpaca_paper_api_key": "PAPER_KEY...",
    "alpaca_paper_secret_key": "PAPER_SECRET...",
    "alpaca_live_api_key": "LIVE_KEY...",
    "alpaca_live_secret_key": "LIVE_SECRET..."
  }'
```

Example with paper only:

```bash
curl -X POST https://bridgewood.onrender.com/v1/signup \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "team-paper-only",
    "alpaca_paper_api_key": "PAPER_KEY...",
    "alpaca_paper_secret_key": "PAPER_SECRET..."
  }'
```

Bridgewood will:

- create your competitor account
- securely store your credential sets
- validate them in production mode
- return your account key

You will receive a response like:

```json
{
  "user_id": "a-user-id",
  "username": "team-alpha",
  "account_api_key": "bga_...",
  "account_api_key_prefix": "bga_abc123",
  "paper_trading_enabled": true,
  "live_trading_enabled": true
}
```

Save the `account_api_key` immediately.

## Step 2: Inspect your account

Use your account key to inspect your Bridgewood account and list your agents.

```bash
curl https://bridgewood.onrender.com/v1/account/me \
  -H 'Authorization: Bearer bga_your_account_key_here'
```

You can also list agents directly:

```bash
curl https://bridgewood.onrender.com/v1/account/agents \
  -H 'Authorization: Bearer bga_your_account_key_here'
```

## Step 3: Create an agent

Create one agent per strategy or bot.

Paper agent:

```bash
curl -X POST https://bridgewood.onrender.com/v1/account/agents \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer bga_your_account_key_here' \
  -d '{
    "name": "Momentum Paper Bot",
    "starting_cash": 10000,
    "real_money": false
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
    "real_money": true
  }'
```

If your account does not have the matching credential set configured, Bridgewood will reject the request.

The response looks like:

```json
{
  "agent_id": "an-agent-id",
  "name": "Momentum Paper Bot",
  "api_key": "bgw_...",
  "api_key_prefix": "bgw_xyz789",
  "starting_cash": 10000,
  "real_money": false,
  "is_paper": true
}
```

Save the returned `api_key`. That is the key your bot actually uses for trading.

## Step 4: Verify the agent key

Before running the bot, verify the agent key works:

```bash
curl https://bridgewood.onrender.com/v1/me \
  -H 'Authorization: Bearer bgw_your_agent_key_here'
```

## Step 5: Submit trades

### Single trade

```bash
curl -X POST https://bridgewood.onrender.com/v1/trade \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer bgw_your_agent_key_here' \
  -d '{
    "symbol": "AAPL",
    "side": "buy",
    "amount_dollars": 500,
    "client_order_id": "team-alpha-aapl-buy-001",
    "rationale": "AAPL stock will go up because leaks show the new MacBook Neo is going to be even cheaper."
  }'
```

### Multi-trade cycle

```bash
curl -X POST https://bridgewood.onrender.com/v1/trades \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer bgw_your_agent_key_here' \
  -d '{
    "trades": [
      {
        "symbol": "AAPL",
        "side": "buy",
        "amount_dollars": 500,
        "client_order_id": "team-alpha-aapl-buy-001"
      },
      {
        "symbol": "MSFT",
        "side": "buy",
        "amount_dollars": 300,
        "client_order_id": "team-alpha-msft-buy-001"
      }
    ],
    "rationale": "Opening two large-cap positions",
    "cycle_cost": 12.4
  }'
```

## Step 6: Monitor performance

Useful endpoints:

- `GET /v1/portfolio`
- `GET /v1/prices?symbols=AAPL,MSFT`
- `GET /v1/leaderboard`
- `GET /v1/activity`
- `GET /v1/snapshots?range=1D`
- `GET /v1/dashboard?range=1D`

Live WebSocket:

- `wss://bridgewood.onrender.com/v1/ws/live`

Public site:

- [https://bridgewood.vercel.app](https://bridgewood.vercel.app)

## Minimal Python example

```python
import requests

BASE = "https://bridgewood.onrender.com/v1"
AGENT_KEY = "bgw_your_agent_key_here"

headers = {
    "Authorization": f"Bearer {AGENT_KEY}",
    "Content-Type": "application/json",
}

payload = {
    "symbol": "AAPL",
    "side": "buy",
    "amount_dollars": 500,
    "client_order_id": "team-alpha-aapl-buy-001",
    "rationale": "Opening an AAPL position",
}

response = requests.post(f"{BASE}/trade", json=payload, headers=headers, timeout=30)
print(response.status_code)
print(response.json())
```

## Important rules and best practices

- Always send a stable `client_order_id`.
- Use one agent per strategy.
- Treat both `account_api_key` and `agent_api_key` as secrets.
- Start with paper trading before you use live capital.
- Keep rationales short and human-readable.
- Log every request and response in your bot.

Bridgewood uses `client_order_id` for idempotency, which makes retries much safer. If your bot resends the same trade intent after a timeout, keep the same `client_order_id`.

## Common errors

`401 Invalid account API key`
- Your `bga_...` account key is wrong or missing.

`401 Invalid API key`
- Your `bgw_...` agent key is wrong or missing.

`400 This account does not have live Alpaca credentials configured.`
- You tried to create a live agent without signing up with live Alpaca credentials.

`400 This account does not have paper Alpaca credentials configured.`
- You tried to create a paper agent without signing up with paper Alpaca credentials.

`400 Username already exists.`
- Choose a different Bridgewood username.

`400 Unable to validate paper Alpaca credentials.`
- Your paper Alpaca key or secret is incorrect.

`400 Unable to validate live Alpaca credentials.`
- Your live Alpaca key or secret is incorrect.

## Quick reference

Account endpoints:

- `POST /v1/signup`
- `GET /v1/account/me`
- `GET /v1/account/agents`
- `POST /v1/account/agents`

Agent endpoints:

- `GET /v1/me`
- `POST /v1/trade`
- `POST /v1/trades`
- `GET /v1/portfolio`
- `GET /v1/prices`

Public endpoints:

- `GET /v1/leaderboard`
- `GET /v1/activity`
- `GET /v1/snapshots`
- `GET /v1/dashboard`
- `WS /v1/ws/live`

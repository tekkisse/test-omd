# OpenMetadata Multi-Site Sync

Event-driven system that syncs OpenMetadata from multiple sites into a central master instance using RabbitMQ as the message bus.

## Architecture

```
[Site A: OpenMetadata] --webhook--> [webhook_receiver SITE_A] --\
[Site B: OpenMetadata] --webhook--> [webhook_receiver SITE_B] ---+--> [RabbitMQ: omd.sync] --> [central_consumer] --> [Central OpenMetadata]
[Site N: OpenMetadata] --webhook--> [webhook_receiver SITE_N] --/
```

Sync is **one-way: site → central**. Each site runs a lightweight webhook receiver; a single central consumer handles all sites.

### FQN transformation

Because every site has identically-named databases, the central OMD prefixes both the database service name and the database name with the site code to avoid collisions:

```
postgres_prod.mydb.public.users
        ↓  (site_code = SITE_A)
SITE_A_postgres_prod.SITE_A_mydb.public.users
```

Schema and table names are left unchanged.

### RabbitMQ routing key layout

```
Exchange : omd.sync  (topic, durable)
Queue    : omd.central.sync  (durable, bound to "#")

Pattern  : {SITE_CODE}.{entityType}.{eventType}

Examples :
  SITE_A.table.EntityCreated
  SITE_B.database.EntityUpdated
  SITE_A.lineage.EntityCreated
```

## Project structure

```
.
├── shared/
│   └── events.py                  # ChangeEvent + SiteEvent pydantic models
├── webhook_receiver/              # FastAPI service — one deployment per site
│   ├── main.py                    # POST /webhook with optional HMAC validation
│   ├── publisher.py               # Auto-reconnecting RabbitMQ publisher
│   ├── config.py                  # Settings via environment variables
│   ├── Dockerfile
│   └── requirements.txt
├── central_consumer/              # Python consumer — runs at central
│   ├── main.py                    # Entry point
│   ├── consumer.py                # Durable RabbitMQ consumer (nack/requeue on failure)
│   ├── sync_handler.py            # Dispatches by entity type, handles deletions
│   ├── transformer.py             # FQN prefix logic
│   ├── omd_client.py              # httpx wrapper for central OMD REST API
│   ├── config.py
│   ├── Dockerfile
│   └── requirements.txt
├── mysql-init/
│   └── init.sql                   # Creates one MySQL database per OMD instance
├── docker-compose.yml             # Full test stack: 3× OMD, MySQL, OpenSearch, RabbitMQ
├── omd_event_subscription_setup.md
├── .env.example
└── README.md
```

## Entity types synced

| Entity type | Notes |
|---|---|
| `databaseService` | Service name prefixed with site code |
| `database` | Name prefixed with site code |
| `databaseSchema` | Parent FQN updated to use prefixed names |
| `table` | Full FQN updated; column definitions included |
| `tag` / `classification` | Synced as-is (treated as global taxonomy) |
| `glossary` / `glossaryTerm` | Synced as-is |
| `lineage` | Edge FQNs transformed to central prefixed names |
| `testCase` / test results | `entityLink` FQN transformed |

Deletions are controlled by `DELETION_STRATEGY` (see configuration below).

## Prerequisites

- Python 3.12+
- Docker + Docker Compose v2
- RabbitMQ 3.11+ reachable from all sites and the central host (provided by Compose for local dev)
- OpenMetadata 1.x at each site and at central (provided by Compose for local dev)

## Quick start (local dev)

The Compose stack spins up the full test environment including three OpenMetadata instances, MySQL, OpenSearch, and RabbitMQ. Every service waits for its dependencies to pass health checks before starting.

```bash
# 1. Enter the project directory
cd omd-sync

# 2. Start the full stack (first run will take 5–10 min for OMD migrations)
docker compose up --build
```

### Service URLs once healthy

| Service | URL | Credentials |
|---|---|---|
| Site A — OpenMetadata | http://localhost:8585 | admin@open-metadata.org / Admin@1234 |
| Site B — OpenMetadata | http://localhost:8586 | admin@open-metadata.org / Admin@1234 |
| Central — OpenMetadata | http://localhost:8587 | admin@open-metadata.org / Admin@1234 |
| Site A — Webhook receiver | http://localhost:8081/health | — |
| Site B — Webhook receiver | http://localhost:8082/health | — |
| RabbitMQ management UI | http://localhost:15672 | omd / omd_secret |
| MySQL | localhost:3306 | root / root_password |
| OpenSearch | http://localhost:9200 | — |

### Startup order

```
mysql ──┐
        ├──> site_a_omd ──> webhook_receiver_site_a ──┐
opensearch ──┤                                         ├──> (events flow)
        ├──> site_b_omd ──> webhook_receiver_site_b ──┤
        └──> central_omd ──> central_consumer ─────────┘
                    ↑
             rabbitmq (all app services also wait on this)
```

### Obtaining the central OMD token for the consumer

After `central_omd` is healthy, fetch a JWT and restart the consumer with it:

```bash
TOKEN=$(curl -s -X POST http://localhost:8587/api/v1/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@open-metadata.org","password":"Admin@1234"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['accessToken'])")

docker compose stop central_consumer
CENTRAL_OMD_TOKEN=$TOKEN docker compose up -d central_consumer
```

### Resource requirements

Running the full stack requires approximately **8 GB RAM** and **4 CPU cores**.

To reduce memory usage you can lower the JVM heap on each OMD instance by adding this environment variable to the three `*_omd` services:

```yaml
OPENMETADATA_HEAP_OPTS: "-Xms512m -Xmx1g"
```

## Running services individually

### Webhook receiver

```bash
cd omd-sync
pip install -r webhook_receiver/requirements.txt

export SITE_CODE=SITE_A
export RABBITMQ_URL=amqp://omd:omd_secret@localhost:5672/
export WEBHOOKSECRET=my-hmac-secret   # optional

PYTHONPATH=. python -m webhook_receiver.main
```

Health check: `GET http://localhost:8080/health`

### Central consumer

```bash
pip install -r central_consumer/requirements.txt

export RABBITMQ_URL=amqp://omd:omd_secret@localhost:5672/
export CENTRAL_OMD_URL=http://central-omd:8585
export CENTRAL_OMD_TOKEN=<jwt-token>

PYTHONPATH=. python -m central_consumer.main
```

## Configuration reference

### Webhook receiver

| Variable | Default | Description |
|---|---|---|
| `SITE_CODE` | **required** | Short unique site identifier, e.g. `SITE_A`. Used as the RabbitMQ routing key prefix and FQN prefix in central OMD. Alphanumeric and underscores only — no dots. |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | RabbitMQ connection URL |
| `RABBITMQ_EXCHANGE` | `omd.sync` | Topic exchange name |
| `WEBHOOK_SECRET` | *(empty)* | HMAC-SHA256 secret configured in the OMD Event Subscription. Leave blank to skip signature validation. |
| `PORT` | `8080` | HTTP listen port |

### Central consumer

| Variable | Default | Description |
|---|---|---|
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | RabbitMQ connection URL |
| `RABBITMQ_EXCHANGE` | `omd.sync` | Must match the exchange used by receivers |
| `RABBITMQ_QUEUE` | `omd.central.sync` | Durable queue name |
| `RABBITMQ_ROUTING_KEY` | `#` | `#` = all sites; `SITE_A.#` = one site; `*.table.*` = tables from all sites |
| `RABBITMQ_PREFETCH` | `10` | Consumer prefetch count |
| `CENTRAL_OMD_URL` | `http://localhost:8585` | Base URL of the central OMD instance |
| `CENTRAL_OMD_TOKEN` | **required** | JWT or API key from the central OMD admin account |
| `DELETION_STRATEGY` | `soft_delete` | What to do when a site deletes an entity: `log` (no action), `soft_delete`, or `hard_delete` |

## OpenMetadata Event Subscription setup

Configure one Event Subscription in each site's OMD UI under **Settings → Integrations → Event Subscriptions → Add Subscription**.

| Field | Value |
|---|---|
| **Name** | `sync-to-central` |
| **Trigger** | All Events |
| **Destination** | Generic Webhook |
| **Endpoint URL** | `http://<webhook-receiver-host>:8080/webhook` |
| **Secret Key** | Same value as `WEBHOOK_SECRET` (leave blank to disable HMAC) |
| **Batch Size** | 10 (tunable) |

### Recommended entity-type filters

Enable at minimum:

- `databaseService` — EntityCreated, EntityUpdated
- `database` — EntityCreated, EntityUpdated, EntityDeleted
- `databaseSchema` — EntityCreated, EntityUpdated, EntityDeleted
- `table` — EntityCreated, EntityUpdated, EntityDeleted
- `lineage` — EntityCreated, EntityUpdated
- `testCase` — EntityCreated, EntityUpdated

Optional (shared taxonomy):

- `classification`, `tag`
- `glossary`, `glossaryTerm`

### Obtaining a Central OMD JWT token

```bash
curl -X POST http://central-omd:8585/api/v1/users/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@open-metadata.org", "password": "Admin@1234"}'
```

Copy `accessToken` from the response and set it as `CENTRAL_OMD_TOKEN`. Tokens expire — use a dedicated bot account and set up token refresh for production.

## Production considerations

### Dead-letter queue

Messages are nacked and requeued on failure. Add a dead-letter exchange to capture messages that fail repeatedly:

```bash
rabbitmqadmin declare exchange name=omd.sync.dlx type=direct durable=true
rabbitmqadmin declare queue name=omd.central.sync.dead durable=true
rabbitmqadmin declare binding source=omd.sync.dlx destination=omd.central.sync.dead
```

Then add `x-dead-letter-exchange: omd.sync.dlx` and `x-message-ttl` to the main queue declaration.

### Token refresh

The central OMD JWT expires. Options:

- Use a service account with a long-lived API key (preferred in OMD 1.3+)
- Wrap `omd_client.py` with a token-refresh interceptor that re-authenticates on 401

### Scaling

The central consumer is a single process but uses `basic_qos` prefetch. To scale horizontally, run multiple `central_consumer` instances — RabbitMQ will round-robin messages across them automatically since they share the same queue.

### Filtering by site

To run a dedicated consumer per site (e.g. for isolation or rate limiting), set `RABBITMQ_ROUTING_KEY=SITE_A.#` and use a unique `RABBITMQ_QUEUE` per consumer.

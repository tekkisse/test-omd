# OpenMetadata Event Subscription Setup

Configure one Event Subscription per site in that site's OMD UI.

## Settings

| Field | Value |
|-------|-------|
| **Name** | `sync-to-central` |
| **Trigger** | All Events (or filter to specific entity types) |
| **Destination** | Generic Webhook |
| **Endpoint URL** | `http://<webhook-receiver-host>:8080/webhook` |
| **Secret Key** | Same value as `WEBHOOK_SECRET` env var (leave blank to skip HMAC) |
| **Batch Size** | 10 (tunable) |
| **Filters** | Add filters for entity types you care about (see below) |

## Recommended entity-type filters

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

## Obtaining a Central OMD JWT token

```bash
curl -X POST http://central-omd:8585/api/v1/users/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@open-metadata.org", "password": "Admin@1234"}'
```

Copy the `accessToken` from the response and set it as `CENTRAL_OMD_TOKEN`.

Tokens expire; use a long-lived bot account or set up token refresh.

## RabbitMQ exchange / routing key layout

```
Exchange : omd.sync  (topic, durable)
Queue    : omd.central.sync  (durable, bound to "#")

Routing key pattern:  {SITE_CODE}.{entityType}.{eventType}

Examples:
  SITE_A.table.EntityCreated
  SITE_B.database.EntityUpdated
  SITE_A.lineage.EntityCreated
```

To consume only a specific site, bind the queue to `SITE_A.#`.
To consume only table events from all sites, bind to `*.table.*`.

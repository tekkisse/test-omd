"""
Dispatches incoming SiteEvents to per-entity-type sync logic.

Each handler receives the *raw* entity dict from the OMD webhook payload and
the site_code, transforms FQNs, then upserts into the central OMD instance.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from shared.events import SiteEvent
from .config import Settings
from .omd_client import OMDClient
from . import transformer as T

logger = logging.getLogger(__name__)


class SyncHandler:
    def __init__(self, client: OMDClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def handle(self, site_event: SiteEvent) -> None:
        event = site_event.event
        site_code = site_event.site_code
        event_type = event.eventType
        entity_type = event.entityType

        logger.info("[%s] %s %s %s", site_code, event_type, entity_type, event.entityFullyQualifiedName)

        if event_type in ("EntityDeleted", "EntitySoftDeleted"):
            self._handle_deletion(entity_type, event.entityFullyQualifiedName, site_code)
            return

        if not event.entity:
            logger.warning("No entity payload for %s %s — skipping", entity_type, event.entityFullyQualifiedName)
            return

        handler = getattr(self, f"_sync_{entity_type}", self._sync_generic)
        try:
            handler(event.entity, site_code)
        except Exception as exc:
            logger.error("Sync failed [%s %s]: %s", entity_type, event.entityFullyQualifiedName, exc, exc_info=True)
            raise

    # ------------------------------------------------------------------
    # Per-entity-type handlers
    # ------------------------------------------------------------------

    def _sync_databaseService(self, entity: Dict[str, Any], site_code: str) -> None:
        payload = T.transform_service(entity, site_code)
        self._upsert("databaseService", payload)

    def _sync_database(self, entity: Dict[str, Any], site_code: str) -> None:
        # Ensure the parent service exists first
        service_ref = entity.get("service", {})
        if service_ref and service_ref.get("type") == "databaseService":
            self._ensure_service(service_ref, site_code)

        payload = T.transform_database(entity, site_code)
        self._upsert("database", payload)

    def _sync_databaseSchema(self, entity: Dict[str, Any], site_code: str) -> None:
        payload = T.transform_schema(entity, site_code)
        self._upsert("databaseSchema", payload)

    def _sync_table(self, entity: Dict[str, Any], site_code: str) -> None:
        payload = T.transform_table(entity, site_code)
        self._upsert("table", payload)

    def _sync_tag(self, entity: Dict[str, Any], site_code: str) -> None:
        # Tags are typically global; sync as-is but de-duplicate by name
        payload = dict(entity)
        payload.pop("id", None)
        self._upsert("tag", payload)

    def _sync_classification(self, entity: Dict[str, Any], site_code: str) -> None:
        payload = dict(entity)
        payload.pop("id", None)
        self._upsert("classification", payload)

    def _sync_glossary(self, entity: Dict[str, Any], site_code: str) -> None:
        payload = dict(entity)
        payload.pop("id", None)
        self._upsert("glossary", payload)

    def _sync_glossaryTerm(self, entity: Dict[str, Any], site_code: str) -> None:
        payload = dict(entity)
        payload.pop("id", None)
        self._upsert("glossaryTerm", payload)

    def _sync_lineage(self, entity: Dict[str, Any], site_code: str) -> None:
        payload = T.transform_lineage(entity, site_code)
        self._client.add_lineage(payload)
        logger.info("Lineage synced for site %s", site_code)

    def _sync_testCase(self, entity: Dict[str, Any], site_code: str) -> None:
        payload = T.transform_test_case(entity, site_code)
        result = self._upsert("testCase", payload)
        # Also sync the latest test result if present
        latest = entity.get("testCaseResult")
        if latest and result:
            try:
                self._client.add_test_result(result["fullyQualifiedName"], latest)
            except Exception as exc:
                logger.warning("Could not sync test result: %s", exc)

    def _sync_generic(self, entity: Dict[str, Any], site_code: str) -> None:
        entity_type = entity.get("entityType", "unknown")
        logger.warning("No specific handler for entity type '%s' — skipping", entity_type)

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def _handle_deletion(self, entity_type: str, fqn: str | None, site_code: str) -> None:
        strategy = self._settings.deletion_strategy
        if strategy == "log" or not fqn:
            logger.info("Deletion event for %s %s — strategy=%s, no action taken", entity_type, fqn, strategy)
            return
        central_fqn = T.transform_fqn(fqn, site_code, entity_type)
        if strategy in ("soft_delete", "hard_delete"):
            self._client.soft_delete(entity_type, central_fqn)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _upsert(self, entity_type: str, payload: Dict[str, Any]) -> Dict[str, Any] | None:
        try:
            result = self._client.put_entity(entity_type, payload)
            logger.debug("Upserted %s %s", entity_type, payload.get("fullyQualifiedName", payload.get("name")))
            return result
        except Exception as exc:
            logger.error("PUT %s failed: %s — payload keys: %s", entity_type, exc, list(payload.keys()))
            raise

    def _ensure_service(self, service_ref: Dict[str, Any], site_code: str) -> None:
        """Create a minimal database service stub if it doesn't exist yet."""
        original_name = service_ref.get("name", "")
        central_name = f"{site_code}_{original_name}"
        existing = self._client.get_by_fqn("databaseService", central_name)
        if existing:
            return
        service_type = service_ref.get("serviceType", "CustomDatabase")
        stub = {
            "name": central_name,
            "serviceType": service_type,
            "description": f"Auto-created stub for site {site_code} service {original_name}",
            "connection": {"config": {"type": service_type}},
        }
        try:
            self._client.put_entity("databaseService", stub)
            logger.info("Created stub service '%s' for site %s", central_name, site_code)
        except Exception as exc:
            logger.warning("Could not create stub service '%s': %s", central_name, exc)

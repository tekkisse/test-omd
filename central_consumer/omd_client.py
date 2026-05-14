"""
Thin httpx wrapper for the OpenMetadata REST API.

Uses PUT (create-or-update) for most entities so the consumer is idempotent —
re-delivering the same event is safe.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# Map OMD entityType → API path
_ENTITY_ENDPOINTS: Dict[str, str] = {
    "databaseService": "/api/v1/services/databaseServices",
    "database": "/api/v1/databases",
    "databaseSchema": "/api/v1/databaseSchemas",
    "table": "/api/v1/tables",
    "tag": "/api/v1/tags",
    "classification": "/api/v1/classifications",
    "glossaryTerm": "/api/v1/glossaryTerms",
    "glossary": "/api/v1/glossaries",
    "testCase": "/api/v1/dataQuality/testCases",
    "testSuite": "/api/v1/dataQuality/testSuites",
}


class OMDClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return self._base + path

    def put_entity(self, entity_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = _ENTITY_ENDPOINTS.get(entity_type)
        if not endpoint:
            raise ValueError(f"No endpoint configured for entity type '{entity_type}'")
        resp = self._client.put(self._url(endpoint), json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_by_fqn(self, entity_type: str, fqn: str) -> Optional[Dict[str, Any]]:
        endpoint = _ENTITY_ENDPOINTS.get(entity_type)
        if not endpoint:
            return None
        resp = self._client.get(self._url(f"{endpoint}/name/{fqn}"))
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def soft_delete(self, entity_type: str, fqn: str) -> None:
        existing = self.get_by_fqn(entity_type, fqn)
        if not existing:
            return
        entity_id = existing["id"]
        endpoint = _ENTITY_ENDPOINTS.get(entity_type, "")
        resp = self._client.delete(self._url(f"{endpoint}/{entity_id}"))
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()
        logger.info("Soft-deleted %s %s", entity_type, fqn)

    def add_lineage(self, payload: Dict[str, Any]) -> None:
        resp = self._client.put(self._url("/api/v1/lineage"), json=payload)
        resp.raise_for_status()

    def add_test_result(self, test_case_fqn: str, result: Dict[str, Any]) -> None:
        resp = self._client.put(
            self._url(f"/api/v1/dataQuality/testCases/{test_case_fqn}/testCaseResult"),
            json=result,
        )
        resp.raise_for_status()

    def close(self) -> None:
        self._client.close()

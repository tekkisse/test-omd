"""
FQN / name transformation logic.

OpenMetadata FQN structure by entity type
------------------------------------------
databaseService  : {service}
database         : {service}.{database}
databaseSchema   : {service}.{database}.{schema}
table            : {service}.{database}.{schema}.{table}
storedProcedure  : {service}.{database}.{schema}.{procedure}

The transformer prefixes the **service name** and the **database name** with the
site code so that identical databases from different sites coexist in the central
OMD without collision.

Example with site_code="SITE_A":
  postgres_prod.mydb.public.users
  →  SITE_A_postgres_prod.SITE_A_mydb.public.users
"""
from __future__ import annotations

import copy
from typing import Any, Dict

# Entity types that have a service + database in their FQN
_DB_ENTITY_TYPES = {"databaseService", "database", "databaseSchema", "table", "storedProcedure"}


def _pfx(name: str, site_code: str) -> str:
    return f"{site_code}_{name}"


def transform_fqn(fqn: str, site_code: str, entity_type: str) -> str:
    """Return the FQN with site-prefixed service and database components."""
    if entity_type not in _DB_ENTITY_TYPES:
        return fqn
    parts = fqn.split(".")
    if len(parts) >= 1:
        parts[0] = _pfx(parts[0], site_code)   # service
    if len(parts) >= 2:
        parts[1] = _pfx(parts[1], site_code)   # database
    return ".".join(parts)


def _transform_entity_ref(ref: Dict[str, Any], site_code: str, ref_type: str) -> Dict[str, Any]:
    """Prefix names / FQNs inside an entity reference dict."""
    ref = copy.copy(ref)
    if ref_type == "databaseService":
        if "name" in ref:
            ref["name"] = _pfx(ref["name"], site_code)
        if "fullyQualifiedName" in ref:
            ref["fullyQualifiedName"] = _pfx(ref["fullyQualifiedName"], site_code)
    elif ref_type == "database":
        if "name" in ref:
            ref["name"] = _pfx(ref["name"], site_code)
        if "fullyQualifiedName" in ref:
            ref["fullyQualifiedName"] = transform_fqn(ref["fullyQualifiedName"], site_code, "database")
    elif ref_type in ("databaseSchema", "table"):
        if "fullyQualifiedName" in ref:
            ref["fullyQualifiedName"] = transform_fqn(ref["fullyQualifiedName"], site_code, ref_type)
    return ref


def transform_service(entity: Dict[str, Any], site_code: str) -> Dict[str, Any]:
    entity = copy.deepcopy(entity)
    entity["name"] = _pfx(entity["name"], site_code)
    entity.pop("id", None)  # let central OMD assign a new id
    return entity


def transform_database(entity: Dict[str, Any], site_code: str) -> Dict[str, Any]:
    entity = copy.deepcopy(entity)
    entity["name"] = _pfx(entity["name"], site_code)
    entity.pop("id", None)
    if "service" in entity and isinstance(entity["service"], dict):
        entity["service"] = _transform_entity_ref(entity["service"], site_code, "databaseService")
    if "fullyQualifiedName" in entity:
        entity["fullyQualifiedName"] = transform_fqn(entity["fullyQualifiedName"], site_code, "database")
    return entity


def transform_schema(entity: Dict[str, Any], site_code: str) -> Dict[str, Any]:
    entity = copy.deepcopy(entity)
    entity.pop("id", None)
    if "database" in entity and isinstance(entity["database"], dict):
        entity["database"] = _transform_entity_ref(entity["database"], site_code, "database")
    if "fullyQualifiedName" in entity:
        entity["fullyQualifiedName"] = transform_fqn(entity["fullyQualifiedName"], site_code, "databaseSchema")
    return entity


def transform_table(entity: Dict[str, Any], site_code: str) -> Dict[str, Any]:
    entity = copy.deepcopy(entity)
    entity.pop("id", None)
    for ref_key, ref_type in (("database", "database"), ("databaseSchema", "databaseSchema")):
        if ref_key in entity and isinstance(entity[ref_key], dict):
            entity[ref_key] = _transform_entity_ref(entity[ref_key], site_code, ref_type)
    if "fullyQualifiedName" in entity:
        entity["fullyQualifiedName"] = transform_fqn(entity["fullyQualifiedName"], site_code, "table")
    # Transform any lineage edges stored on the entity
    for edge_list_key in ("upstreamLineage", "downstreamLineage"):
        for edge in entity.get(edge_list_key, []):
            for ep_key in ("fromEntity", "toEntity"):
                ep = edge.get(ep_key, {})
                if "fullyQualifiedName" in ep:
                    ep["fullyQualifiedName"] = transform_fqn(
                        ep["fullyQualifiedName"], site_code, ep.get("type", "table")
                    )
    return entity


def transform_lineage(lineage: Dict[str, Any], site_code: str) -> Dict[str, Any]:
    """Transform an AddLineageRequest payload."""
    lineage = copy.deepcopy(lineage)
    for ep_key in ("fromEntity", "toEntity"):
        ep = lineage.get("edge", {}).get(ep_key, {})
        if "fullyQualifiedName" in ep:
            ep["fullyQualifiedName"] = transform_fqn(
                ep["fullyQualifiedName"], site_code, ep.get("type", "table")
            )
    return lineage


def transform_test_case(entity: Dict[str, Any], site_code: str) -> Dict[str, Any]:
    """Prefix the entityLink table FQN inside a test case."""
    entity = copy.deepcopy(entity)
    entity.pop("id", None)
    # entityLink format: <#E::table::service.db.schema.table::column>
    link: str = entity.get("entityLink", "")
    if link:
        parts = link.split("::")
        if len(parts) >= 3:
            parts[2] = transform_fqn(parts[2], site_code, "table")
            entity["entityLink"] = "::".join(parts)
    return entity

"""Offline Schema.org JSON-LD validation backed by the bundled ontology."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_ONTOLOGY_FILE = Path(__file__).resolve().parent / "data" / "schema_master.json"


@lru_cache(maxsize=1)
def load_ontology() -> dict[str, dict[str, list[str]]]:
    if not _ONTOLOGY_FILE.exists():
        return {}

    with _ONTOLOGY_FILE.open("r", encoding="utf-8") as file:
        raw_data = json.load(file)

    ontology: dict[str, dict[str, list[str]]] = {}
    for node in raw_data.get("@graph", []):
        node_id = node.get("@id", "")
        node_types = node.get("@type", [])
        if isinstance(node_types, str):
            node_types = [node_types]
        if not node_id.startswith("schema:") or "rdfs:Class" not in node_types:
            continue

        class_name = node_id.removeprefix("schema:")
        parents = node.get("rdfs:subClassOf", [])
        if isinstance(parents, dict):
            parents = [parents]
        ontology[class_name] = {
            "parents": [
                parent.get("@id", "").removeprefix("schema:")
                for parent in parents
                if isinstance(parent, dict)
            ],
            "properties": [],
        }

    for node in raw_data.get("@graph", []):
        node_id = node.get("@id", "")
        node_types = node.get("@type", [])
        if isinstance(node_types, str):
            node_types = [node_types]
        if not node_id.startswith("schema:") or "rdf:Property" not in node_types:
            continue

        property_name = node_id.removeprefix("schema:")
        domains = node.get("schema:domainIncludes", [])
        if isinstance(domains, dict):
            domains = [domains]
        for domain in domains:
            if not isinstance(domain, dict):
                continue
            class_name = domain.get("@id", "").removeprefix("schema:")
            if class_name in ontology:
                ontology[class_name]["properties"].append(property_name)

    return ontology


def _allowed_properties(
    schema_type: str,
    ontology: dict[str, dict[str, list[str]]],
    visiting: set[str] | None = None,
) -> set[str]:
    if schema_type not in ontology:
        return set()

    active = set() if visiting is None else visiting
    if schema_type in active:
        return set()
    active.add(schema_type)

    allowed = set(ontology[schema_type]["properties"])
    for parent in ontology[schema_type]["parents"]:
        allowed.update(_allowed_properties(parent, ontology, active))
    active.remove(schema_type)
    return allowed


def _normalize_type(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("schema:"):
        return normalized.removeprefix("schema:")
    return normalized.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def _typed_nodes(value: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            nodes.extend(_typed_nodes(item))
    elif isinstance(value, dict):
        if "@type" in value:
            nodes.append(value)
        for child in value.values():
            if isinstance(child, (dict, list)):
                nodes.extend(_typed_nodes(child))
    return nodes


def _empty_details() -> dict[str, list[str]]:
    return {"valid_fields": [], "invalid_fields": []}


def validate_schemas(raw_schemas: list[str]) -> list[dict[str, Any]]:
    ontology = load_ontology()
    results: list[dict[str, Any]] = []

    for raw_schema in raw_schemas:
        try:
            document = json.loads(raw_schema)
        except json.JSONDecodeError as exc:
            results.append(
                {
                    "type": "Parse Error",
                    "syntax_valid": False,
                    "structure_status": "Invalid JSON-LD syntax.",
                    "details": _empty_details(),
                    "error_detail": str(exc),
                }
            )
            continue

        nodes = _typed_nodes(document)
        if not nodes:
            results.append(
                {
                    "type": "Unknown",
                    "syntax_valid": True,
                    "structure_status": "Warning: JSON-LD block has no @type.",
                    "details": _empty_details(),
                    "error_detail": None,
                }
            )
            continue

        for node in nodes:
            raw_types = node.get("@type", "Unknown")
            if not isinstance(raw_types, list):
                raw_types = [raw_types]
            schema_types = [
                _normalize_type(value) for value in raw_types if isinstance(value, str)
            ] or ["Unknown"]
            recognized_types = [value for value in schema_types if value in ontology]
            display_type = ", ".join(schema_types)

            if not recognized_types:
                results.append(
                    {
                        "type": display_type,
                        "syntax_valid": True,
                        "structure_status": (
                            f"Warning: '{display_type}' is not a recognized Schema.org type."
                        ),
                        "details": _empty_details(),
                        "error_detail": None,
                    }
                )
                continue

            allowed: set[str] = set()
            for schema_type in recognized_types:
                allowed.update(_allowed_properties(schema_type, ontology))

            fields = sorted(key for key in node if not key.startswith("@"))
            valid_fields = [field for field in fields if field in allowed]
            invalid_fields = [field for field in fields if field not in allowed]
            structure_status = (
                f"Properties not recognized for this type: {', '.join(invalid_fields)}"
                if invalid_fields
                else (
                    "Type and property names are recognized. Value types, required or "
                    "recommended fields, and rich-result eligibility were not validated."
                )
            )
            results.append(
                {
                    "type": display_type,
                    "syntax_valid": True,
                    "structure_status": structure_status,
                    "details": {
                        "valid_fields": valid_fields,
                        "invalid_fields": invalid_fields,
                    },
                    "error_detail": None,
                }
            )

    return results

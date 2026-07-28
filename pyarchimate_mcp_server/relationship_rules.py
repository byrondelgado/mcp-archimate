"""Versioned ArchiMate relationship rule helpers."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any

from pyArchimate.constants import ARCHI_CATEGORY
from pyArchimate.exceptions import ArchimateConceptTypeError, ArchimateRelationshipError
from pyArchimate.relationship import (
    ALLOWED_RELATIONSHIPS,
    RELATIONSHIP_KEYS,
    check_valid_relationship,
)

ARCHIMATE_VERSION = "3.2-compatible"
SUPPORTED_INTENTS = {
    "serves",
    "uses_data",
    "writes_data",
    "reads_data",
    "realizes",
    "assigned_to",
    "flows_to",
    "influences",
    "associated_with",
    "deployed_on",
    "technology_supports_application",
    "application_supports_business",
}

INTENT_RELATIONSHIP_TYPES = {
    "serves": ["Serving"],
    "application_supports_business": ["Serving"],
    "technology_supports_application": ["Serving", "Realization"],
    "deployed_on": ["Serving", "Realization", "Assignment"],
    "uses_data": ["Access"],
    "reads_data": ["Access"],
    "writes_data": ["Access"],
    "realizes": ["Realization"],
    "assigned_to": ["Assignment"],
    "flows_to": ["Flow", "Triggering"],
    "influences": ["Influence"],
    "associated_with": ["Association"],
}

ACCESS_TYPE_BY_INTENT = {
    "reads_data": "Read",
    "writes_data": "Write",
    "uses_data": "Access",
}

_RELATIONSHIP_BY_KEY = {value: key for key, value in RELATIONSHIP_KEYS.items()}


def backend_metadata() -> dict[str, Any]:
    """Return version metadata for the active rule source."""
    try:
        backend_version = version("pyArchimate")
    except PackageNotFoundError:
        backend_version = "unknown"
    return {
        "archimate_version": ARCHIMATE_VERSION,
        "backend": f"pyArchimate {backend_version}",
        "rule_source": "pyArchimate.relationship.ALLOWED_RELATIONSHIPS",
        "supported_intents": sorted(SUPPORTED_INTENTS),
    }


def valid_relationship_types(source_type: str, target_type: str) -> list[str]:
    """Return valid relationship types for a source/target type pair."""
    normalized_source = _normalize_matrix_type(source_type)
    normalized_target = _normalize_matrix_type(target_type)
    keys = ALLOWED_RELATIONSHIPS.get(normalized_source, {}).get(normalized_target, "")
    return sorted(
        _RELATIONSHIP_BY_KEY[key] for key in keys if key in _RELATIONSHIP_BY_KEY
    )


def is_valid_relationship(
    relationship_type: str,
    source_type: str,
    target_type: str,
) -> tuple[bool, str | None]:
    """Return whether the relationship is valid and any validation message."""
    try:
        check_valid_relationship(
            relationship_type,
            source_type,
            target_type,
            raise_flg=True,
        )
    except (ArchimateConceptTypeError, ArchimateRelationshipError) as exc:
        return False, str(exc)
    return True, None


def compatibility(source_type: str, target_type: str) -> dict[str, Any]:
    """Return public compatibility metadata for a source/target type pair."""
    return {
        **backend_metadata(),
        "source_type": source_type,
        "target_type": target_type,
        "valid_relationships": [
            {
                "type": relationship_type,
                "direction": "source_to_target",
                "required_attributes": required_attributes(relationship_type),
                "relationship_attributes": relationship_attributes(relationship_type),
            }
            for relationship_type in valid_relationship_types(source_type, target_type)
        ],
    }


def recommendations(
    source_type: str,
    target_type: str,
    *,
    intent: str | None = None,
    strict_archimate: bool = True,
) -> dict[str, Any]:
    """Recommend valid relationship options for source/target types."""
    normalized_intent = None if intent is None else str(intent)
    preferred_types = INTENT_RELATIONSHIP_TYPES.get(normalized_intent, [])
    options = []
    options.extend(
        _recommendation_options(
            source_type,
            target_type,
            "source_to_target",
            preferred_types,
            normalized_intent,
        ),
    )
    options.extend(
        _recommendation_options(
            target_type,
            source_type,
            "target_to_source",
            preferred_types,
            normalized_intent,
        ),
    )

    if preferred_types:
        matching_options = [
            option for option in options if option["type"] in preferred_types
        ]
        if matching_options:
            options = matching_options
    elif strict_archimate:
        options = [
            option for option in options if option["confidence"] in {"high", "medium"}
        ]

    options = _deduplicate_options(options)
    return {
        **backend_metadata(),
        "source_type": source_type,
        "target_type": target_type,
        "intent": normalized_intent,
        "strict_archimate": strict_archimate,
        "recommendations": options,
        "requires_judgment": len(options) != 1,
    }


def relationship_issue_details(  # noqa: PLR0913
    relationship_type: str,
    source_type: str,
    target_type: str,
    *,
    source_id: str | None = None,
    target_id: str | None = None,
    source_name: str | None = None,
    target_name: str | None = None,
    relationship_id: str | None = None,
    relationship_name: str | None = None,
) -> dict[str, Any]:
    """Build structured details for an invalid relationship."""
    valid, message = is_valid_relationship(relationship_type, source_type, target_type)
    alternatives = valid_alternatives(source_type, target_type)
    repairs = deterministic_repairs(
        relationship_type,
        source_type,
        target_type,
        source_id=source_id,
        target_id=target_id,
        relationship_id=relationship_id,
    )
    return {
        "code": "INVALID_RELATIONSHIP_COMBINATION",
        "severity": "error",
        "valid": valid,
        "message": message
        or (f"{relationship_type} is valid from {source_type} to {target_type}."),
        "relationship_id": relationship_id,
        "relationship_name": relationship_name,
        "relationship_type": relationship_type,
        "source_element_id": source_id,
        "source_name": source_name,
        "source_type": source_type,
        "target_element_id": target_id,
        "target_name": target_name,
        "target_type": target_type,
        "valid_alternatives": alternatives,
        "suggested_repairs": repairs,
        "requires_decision": not any(repair["deterministic"] for repair in repairs),
    }


def valid_alternatives(source_type: str, target_type: str) -> list[dict[str, Any]]:
    """Return valid alternatives in both directions."""
    alternatives = [
        {
            "type": relationship_type,
            "direction": "source_to_target",
            "source_type": source_type,
            "target_type": target_type,
            "required_attributes": required_attributes(relationship_type),
        }
        for relationship_type in valid_relationship_types(source_type, target_type)
    ]
    alternatives.extend(
        {
            "type": relationship_type,
            "direction": "target_to_source",
            "source_type": target_type,
            "target_type": source_type,
            "required_attributes": required_attributes(relationship_type),
        }
        for relationship_type in valid_relationship_types(target_type, source_type)
    )
    return alternatives


def deterministic_repairs(  # noqa: PLR0913
    relationship_type: str,
    source_type: str,
    target_type: str,
    *,
    source_id: str | None,
    target_id: str | None,
    relationship_id: str | None,
) -> list[dict[str, Any]]:
    """Return deterministic repair candidates for common invalid patterns."""
    repairs: list[dict[str, Any]] = []

    def add_repair(  # noqa: PLR0913
        *,
        action: str,
        new_type: str,
        new_source_id: str | None,
        new_target_id: str | None,
        reason: str,
        access_type: str | None = None,
    ) -> None:
        if new_source_id is None or new_target_id is None:
            return
        repair_id = (
            f"repair-{relationship_id or 'relationship'}-{action}-"
            f"{new_type}-{new_source_id}-{new_target_id}"
        )
        repair = {
            "repair_id": repair_id,
            "action": action,
            "new_type": new_type,
            "new_source_id": new_source_id,
            "new_target_id": new_target_id,
            "confidence": "high",
            "deterministic": True,
            "reason": reason,
        }
        if access_type is not None:
            repair["access_type"] = access_type
        repairs.append(repair)

    if (
        relationship_type == "Access"
        and source_type == "BusinessProcess"
        and target_type == "ApplicationService"
        and "Serving" in valid_relationship_types(target_type, source_type)
    ):
        add_repair(
            action="replace_relationship",
            new_type="Serving",
            new_source_id=target_id,
            new_target_id=source_id,
            reason="Application services commonly serve business behavior.",
        )

    if (
        relationship_type == "Flow"
        and source_type == "BusinessProcess"
        and target_type == "BusinessObject"
        and "Access" in valid_relationship_types(source_type, target_type)
    ):
        add_repair(
            action="replace_relationship",
            new_type="Access",
            new_source_id=source_id,
            new_target_id=target_id,
            access_type="Access",
            reason="Business behavior accesses passive business objects.",
        )

    if relationship_type == "Realization" and "Realization" in valid_relationship_types(
        target_type, source_type
    ):
        add_repair(
            action="reverse_relationship",
            new_type="Realization",
            new_source_id=target_id,
            new_target_id=source_id,
            reason="The requested Realization is valid in the reverse direction.",
        )

    if (
        relationship_type == "Realization"
        and source_type == "ApplicationComponent"
        and target_type == "Node"
        and "Serving" in valid_relationship_types(target_type, source_type)
    ):
        add_repair(
            action="replace_relationship",
            new_type="Serving",
            new_source_id=target_id,
            new_target_id=source_id,
            reason="Technology nodes can serve application components.",
        )

    if (
        relationship_type == "Assignment"
        and source_type in {"Node", "Device", "SystemSoftware"}
        and target_type in {"ApplicationComponent", "ApplicationCollaboration"}
        and "Serving" in valid_relationship_types(source_type, target_type)
    ):
        add_repair(
            action="replace_relationship",
            new_type="Serving",
            new_source_id=source_id,
            new_target_id=target_id,
            reason=(
                "A technology node that hosts or runs an application "
                "component serves it; Assignment is not allowed here."
            ),
        )

    return _deduplicate_repairs(repairs)


def required_attributes(relationship_type: str) -> list[str]:
    """Return attributes required for strict creation by relationship type."""
    if relationship_type == "Access":
        return ["access_type"]
    return []


def relationship_attributes(relationship_type: str) -> dict[str, Any]:
    """Return known relationship-specific attribute metadata."""
    if relationship_type == "Access":
        return {"access_type": ["Access", "Read", "ReadWrite", "Write"]}
    if relationship_type == "Influence":
        return {"influence_strength": ["+", "++", "-", "--", *map(str, range(11))]}
    if relationship_type == "Association":
        return {"is_directed": [True, False]}
    return {}


def _recommendation_options(
    source_type: str,
    target_type: str,
    direction: str,
    preferred_types: list[str],
    intent: str | None,
) -> list[dict[str, Any]]:
    options = []
    for relationship_type in valid_relationship_types(source_type, target_type):
        confidence = "high" if relationship_type in preferred_types else "medium"
        option = {
            "type": relationship_type,
            "direction": direction,
            "source_type": source_type,
            "target_type": target_type,
            "confidence": confidence,
            "recommended": relationship_type in preferred_types,
            "reason": _recommendation_reason(relationship_type, intent),
            "required_attributes": required_attributes(relationship_type),
            "attributes": {},
        }
        access_type = ACCESS_TYPE_BY_INTENT.get(intent or "")
        if relationship_type == "Access" and access_type is not None:
            option["attributes"]["access_type"] = access_type
        options.append(option)
    return options


def _recommendation_reason(relationship_type: str, intent: str | None) -> str:
    if intent is not None:
        return f"{relationship_type} matches intent {intent!r} when valid."
    return f"{relationship_type} is valid for this source/target pair."


def _normalize_matrix_type(concept_type: str) -> str:
    if concept_type not in ARCHI_CATEGORY:
        return concept_type
    if ARCHI_CATEGORY[concept_type] == "Relationship":
        return "Relationship"
    if "Junction" in concept_type:
        return "Junction"
    return concept_type


def _deduplicate_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for option in options:
        key = (option["type"], option["direction"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(option)
    return unique


def _deduplicate_repairs(repairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for repair in repairs:
        key = (
            repair["action"],
            repair["new_type"],
            repair["new_source_id"],
            repair["new_target_id"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(repair)
    return unique

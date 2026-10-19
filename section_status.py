"""Informational status rows for the registered-section catalogue."""
from __future__ import annotations

from datetime import date
from importlib.metadata import PackageNotFoundError, version
from typing import Iterable, Mapping


UNKNOWN = "Unknown"
PASSED = "Passed"

# These are exact provider identities from the validation record.  Evidence is
# patch-level and deliberately does not imply that an entire section is valid.
HISTORICAL_EVIDENCE: dict[str, dict[str, dict[str, str]]] = {
    "73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126": {
        "fetch": {
            "status": PASSED,
            "date": "2026-10-19",
            "software": "siibra 1.0.1-alpha.25",
            "evidence_reference": "VALIDATION.md · Direct siibra comparison",
            "scope": "bounded patch evidence only",
        },
        "export": {
            "status": PASSED,
            "date": "2026-10-19",
            "software": "Python 3.12.3; nibabel 5.4.2",
            "evidence_reference": "VALIDATION.md · corrected one-section ZIP",
            "scope": "one exported patch, not the whole section",
        },
    },
    "73c1fa55-d099-4854-8cda-c9a403c6080a--b0738367ed7b5255928960dd9b97f16f": {
        "fetch": {
            "status": PASSED,
            "date": "2026-10-19",
            "software": "siibra 1.0.1-alpha.25",
            "evidence_reference": "SECTION_CATALOGUE_VALIDATION.md · bounded #3500 fetch",
            "scope": "bounded patch evidence only",
        },
    },
}


def software_versions() -> str:
    values = []
    for package in ("siibra", "numpy", "nibabel"):
        try:
            value = version(package)
        except PackageNotFoundError:
            value = "unavailable"
        values.append(f"{package} {value}")
    return "; ".join(values)


def _evidence(status: str, evidence_date: str, software: str, reference: str, scope: str) -> dict[str, str]:
    return {
        "status": status,
        "date": evidence_date,
        "software": software,
        "evidence_reference": reference,
        "scope": scope,
    }


def section_status_rows(
    catalogue: Iterable[Mapping],
    current_fetch_ids: Iterable[str] = (),
    collection: Mapping[str, Mapping] | None = None,
    today: str | None = None,
) -> list[dict[str, object]]:
    """Build display-ready rows keyed by exact provider section identity."""
    current_date = today or date.today().isoformat()
    current_software = software_versions()
    current_fetch = set(current_fetch_ids)
    collection = collection or {}
    collected_ids = {str(entry.get("metadata", {}).get("section_id")) for entry in collection.values()}
    rows = []
    for item in catalogue:
        section_id = str(item.get("id", ""))
        historical = HISTORICAL_EVIDENCE.get(section_id, {})
        discovered_status = PASSED if item.get("metadata_retrieval_status") == "verified from installed siibra configuration" else UNKNOWN
        discovered = _evidence(
            discovered_status,
            current_date,
            current_software,
            "installed siibra configuration · registered-section catalogue",
            "provider metadata discovery only",
        )
        if section_id in current_fetch:
            fetch = _evidence(PASSED, current_date, current_software, "current session provider fetch", "bounded patch evidence only")
        else:
            fetch = historical.get("fetch", _evidence(UNKNOWN, "unknown", "unknown", "No fetch evidence recorded", "not tested"))
        if section_id in collected_ids:
            export = _evidence(PASSED, current_date, current_software, "current session collection entry", "one exported patch, not the whole section")
        else:
            export = historical.get("export", _evidence(UNKNOWN, "unknown", "unknown", "No export-integrity evidence recorded", "not tested"))
        anatomical = _evidence(UNKNOWN, "unknown", "unknown", "No independent anatomical review", "not reviewed")
        rows.append({
            "section_id": section_id,
            "section": f"#{item.get('section_number', '?')}",
            "world_Y_mm": round(float(item["section_plane_y_mm"]), 4),
            "provider": item.get("source_url", ""),
            "discovered": discovered["status"],
            "discovered_date": discovered["date"],
            "discovered_software": discovered["software"],
            "discovered_evidence": discovered["evidence_reference"],
            "fetch_evidence": fetch["status"],
            "fetch_date": fetch["date"],
            "fetch_software": fetch["software"],
            "fetch_evidence_reference": fetch["evidence_reference"],
            "fetch_scope": fetch["scope"],
            "export_integrity": export["status"],
            "export_date": export["date"],
            "export_software": export["software"],
            "export_evidence_reference": export["evidence_reference"],
            "export_scope": export["scope"],
            "anatomical_review": anatomical["status"],
            "anatomical_review_date": anatomical["date"],
            "anatomical_review_evidence": anatomical["evidence_reference"],
        })
    return sorted(rows, key=lambda row: (float(row["world_Y_mm"]), str(row["section_id"])))


def filter_section_status_rows(rows: Iterable[Mapping], evidence_filter: str = "All", y_range: tuple[float, float] | None = None) -> list[dict]:
    """Filter status rows without altering catalogue or selection state."""
    fields = {
        "Discovered": "discovered",
        "Fetch evidence": "fetch_evidence",
        "Export integrity": "export_integrity",
        "Independent anatomical review": "anatomical_review",
    }
    result = []
    for row in rows:
        if evidence_filter != "All" and row[fields[evidence_filter]] != PASSED:
            continue
        if y_range is not None and not (y_range[0] <= float(row["world_Y_mm"]) <= y_range[1]):
            continue
        result.append(dict(row))
    return result

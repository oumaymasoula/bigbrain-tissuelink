from section_status import PASSED, UNKNOWN, filter_section_status_rows, section_status_rows


ID_3458 = "73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126"


def _catalogue():
    return [
        {
            "id": ID_3458,
            "section_number": 3458,
            "section_plane_y_mm": -0.8595,
            "source_url": "https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed",
            "metadata_retrieval_status": "verified from installed siibra configuration",
        },
        {
            "id": "unseen-section-id",
            "section_number": 9999,
            "section_plane_y_mm": 12.0,
            "source_url": "https://1um.brainatlas.eu/registered_sections/bigbrain/B20_9999/precomputed",
            "metadata_retrieval_status": "not verified",
        },
    ]


def test_status_loading_separates_discovery_fetch_export_and_review():
    rows = section_status_rows(_catalogue(), today="2026-10-20")
    known = next(row for row in rows if row["section_id"] == ID_3458)
    unseen = next(row for row in rows if row["section_id"] == "unseen-section-id")
    assert known["discovered"] == PASSED
    assert known["fetch_evidence"] == PASSED  # historical patch evidence
    assert known["export_integrity"] == PASSED  # one historical patch only
    assert known["anatomical_review"] == UNKNOWN
    assert known["fetch_scope"] == "bounded patch evidence only"
    assert unseen["discovered"] == UNKNOWN
    assert unseen["fetch_evidence"] == UNKNOWN
    assert unseen["export_integrity"] == UNKNOWN
    assert unseen["anatomical_review"] == UNKNOWN


def test_current_fetch_and_collection_evidence_are_scoped_to_exact_section_id():
    rows = section_status_rows(
        _catalogue(),
        current_fetch_ids={ID_3458},
        collection={"patch": {"metadata": {"section_id": ID_3458}}},
        today="2026-10-20",
    )
    row = next(item for item in rows if item["section_id"] == ID_3458)
    assert row["fetch_date"] == "2026-10-20"
    assert row["export_date"] == "2026-10-20"
    assert row["export_scope"] == "one exported patch, not the whole section"
    assert next(item for item in rows if item["section_id"] == "unseen-section-id")["fetch_evidence"] == UNKNOWN


def test_status_filters_do_not_change_rows_or_identity():
    rows = section_status_rows(_catalogue(), today="2026-10-20")
    discovered = filter_section_status_rows(rows, "Discovered", (-1.0, 0.0))
    assert [row["section_id"] for row in discovered] == [ID_3458]
    assert filter_section_status_rows(rows, "Fetch evidence", (-100.0, 100.0))[0]["section_id"] == ID_3458
    assert all("section_id" in row for row in rows)

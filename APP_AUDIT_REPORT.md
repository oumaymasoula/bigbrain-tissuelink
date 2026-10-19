# BigBrain TissueLink application audit

Date: 2026-10-19

## Result

The application is technically healthy for its documented experimental scope.
The complete automated suite passed: **80 tests passed in 1.58 seconds**. All
three navigation targets started without exceptions when the public siibra
configuration service was reachable. No merge or deployment was performed.

Anatomical claims remain deliberately limited. The detailed-section mapping,
regional overlays and transformed ROIs are technical spatial evidence and
remain awaiting independent anatomical review.

## Page review

### MRI–Histology Explorer

- Loads the local donor MRI and 200 µm reconstructed histology volumes.
- Discovers 145 registered sections from siibra when its public configuration
  service is available.
- Preserves explicit section selection, linked reference navigation, bounded
  detailed fetches, patch statistics, collection addition/export, sampling,
  annotation import and collection replay.
- Correctly keeps current selection state separate from collected patches.
- Requires network access for siibra configuration/provider operations. An
  offline AppTest failed at configuration discovery; the same startup passed
  with network access and loaded all 145 sections.

### Experimental template ROI

- Starts with checksum verification of the preserved CerebrA example and does
  not rerun its historical transform.
- Keeps new uploads gated behind explicit ICBM2009c symmetric template
  declaration, provenance and binary/geometry/request validation.
- Clearly identifies the transformed 2 mm mask as coarse candidate placement,
  not an exact anatomical boundary.
- Provides translucent overlays, scientific NIfTI downloads, intersecting
  sections, bounded fetching, shared collection addition and collection ZIP
  export.
- Changing ROI or selected section clears stale current-patch state without
  deleting the collection.
- Anatomical placement remains awaiting independent review.

### Alignment review (advanced)

- Starts without exceptions using the local reference volumes.
- Keeps manual point-pair inspection separate from the primary workflow.
- Reports geometry and visual overlays without converting them into an
  anatomical-validation claim.

## Validation performed

```text
pytest: 80 passed
Python compilation: navigation and all three pages passed
git diff --check: passed
navigation AppTest with public siibra access: passed, 145 sections loaded
Alignment page AppTest: passed
Experimental ROI page AppTest: passed
```

Browser-control automation remained unreliable in this session, so this audit
does not claim a newly completed browser-download round trip. Existing browser
limitations and the manual checklist remain documented in
`BROWSER_ROI_VERIFICATION.md`.

## Cleanup

Removed only reproducible or redundant files:

- `.pytest_cache/`
- root, page and test `__pycache__/` directories
- root-level `bigbrain tissueLink.png`, which was untracked, unreferenced and
  byte-for-byte identical to `assets/bigbrain-tissuelink-logo.png`
- one unused Python import

The deleted duplicate logo is recoverable by copying the canonical asset. No
source module, documentation, test, environment, scientific volume, exported
patch, transform output, validation evidence or collection artifact was
deleted.

## Remaining maintenance notes

- Streamlit reports that `use_container_width` is deprecated after
  2025-12-31. The current installed version still supports it, so this is
  maintenance debt rather than a current failure.
- Provider-backed workflows depend on public siibra and image-provider
  availability.
- Independent anatomical review is still required before any transformed ROI
  placement is described as anatomically accurate.

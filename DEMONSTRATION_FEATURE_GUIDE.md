# BigBrain TissueLink demonstration feature guide

| Feature | Purpose | Expected output | Verification status |
|---|---|---|---|
| MRI–Histology Explorer | Choose a registered section and tissue location. | Linked reference views and a bounded detailed patch. | Implemented; section 3458 manual patch exercised successfully and retained in the corrected collection ZIP. |
| Inspect selected tissue | Review the detailed registered-section image before collection. | Marked preview, unmarked source-plane preview, coordinates, bounds and native resolution. | Implemented; exercised successfully for the retained section 3458 patch. |
| Patch collection | Preserve inspected patches independently of the current selection. | Multiple manual and/or ROI patch entries with per-patch metadata. | Implemented; automated mixed-route and state-preservation tests pass. |
| Collection ZIP export | Export raw NIfTI, PNGs and machine-readable metadata. | Offline ZIP with per-patch files and manifest. | Implemented; exercised successfully by automated checksum/manifest tests and an existing corrected collection ZIP. |
| Visual HTML report | Present collection results without the app or internet. | One self-contained HTML file with embedded previews, route, geometry, checksums and provenance. | Implemented; exercised successfully with retained manual and ROI artifacts and opened offline in Firefox. |
| Load technically verified CerebrA example | Open the preserved left-precentral ROI evidence without rerunning its transform. | Source/BigBrain overlays, intersecting sections and saved patch evidence. | Implemented; preserved checksums and automated end-to-end loader tests pass. Anatomical placement remains awaiting independent review. |
| New binary ROI upload | Validate and transform a user-declared ROI on the exact supported ICBM2009c symmetric 1 mm template. | Logged transform run and checksum-bound source/transformed overlays. | Implemented and validator exercised. One historical uploaded run has mismatched free-text provenance and must not be treated as a valid cuneus result; a correctly identified new uploaded ROI run remains unverified. |
| ROI section intersection and bounded fetch | Find registered sections crossing a transformed ROI and inspect tissue at actual mask coverage. | Section list, coverage counts and bounded patch preview. | Exercised successfully for the preserved CerebrA example (section 3146); anatomical accuracy is not claimed. |
| Alignment review (advanced) | Inspect MRI/BigBrain agreement and known limitations. | Side-by-side, overlay and diagnostic views. | Implemented; saved diagnostic outputs exist. Independent anatomical validation remains unverified. |
| Annotation import/export (advanced) | Connect collection planes to Labelme/COCO workflows. | Validated annotation packages tied to the exact PNG and patch ID. | Implemented and automated tests pass; external annotator round-trip is not part of this demonstration report. |

## Primary demonstration

Choose tissue → inspect the returned patch and geometry → add it to the collection → export the ZIP or offline visual report.

## Limitations

- BigBrain is reference tissue from one donor, not patient data or a clinical tool.
- MRI–histology alignment and ROI placement require independent anatomical review.
- Historical entries can only report fields retained at collection time; absent information is shown as **Not recorded**.
- The preserved ROI patch did not retain its annotation-plane mapping or an unmarked patch PNG.

# BigBrain TissueLink automated demonstration execution report

- Started: `2026-10-19T19:22:02.691279+00:00`
- Finished: `2026-10-19T19:26:42.801490+00:00`
- Browser: Google Chrome (resolved by the automation environment)
- Viewport/video: `1920 × 1080`, silent
- Application: `http://127.0.0.1:8513/`
- Video: `demo/bigbrain_tissuelink_complete_demo.mp4` (generated locally; excluded from Git)
- Video verification: **passed** — FFmpeg return code 0; 14122553 bytes
- Media inspection: H.264 High, 1920 × 1080, 25 fps, yuv420p, 243.24 seconds (4:03), one video stream and no audio stream.
- Timeline inspection: six frames spanning the recording were decoded and reviewed in `demo/verification_frames/timeline_montage.png`; the real application, MRI/histology imagery, ROI controls/results, provenance, and alignment review rendered without blank or corrupted frames.
- Scientific-data policy: preserved left-precentral transform loaded by checksum; new upload used the documented right-cuneus compatible mask.

## Recorded steps

| Step | Status | Detail |
|---|---|---|
| MRI–Histology Explorer loaded | passed | http://127.0.0.1:8513/ |
| registered section selection | passed | Opened the real section catalogue; retained documented section 3458 |
| detailed tissue centre selection | passed | Selected a live point in the registered section |
| real manual patch fetch | passed | Bounded registered-section patch rendered |
| manual patch collection | passed | Patch added to shared collection |
| atlas navigation | passed | Displayed the available atlas-region selector and real section-mask check control |
| MRI overview navigation | passed | Moved shared X/Z location using the live MRI overview |
| linked histology navigation | passed | Moved the same shared location from the histology overview |
| location saving | passed | Saved shared-coordinate inspection location |
| download manual_collection | failed | Download.save_as: canceled |
| download manual_report | failed | Download.save_as: canceled |
| Experimental template ROI loaded | passed | http://127.0.0.1:8513/Experimental_ROI |
| verified CerebrA example | passed | Preserved checksums verified; historical transform not repeated |
| verified ROI patch workflow | passed | Section 3146 patch fetched and added to the same collection |
| compatible ROI upload | passed | cerebra_right_cuneus_icbm2009c_sym_1mm_binary_roi.nii.gz; exact documented template and provenance |
| real uploaded ROI transform | passed | Pinned BigBrainWarp container completed |
| download mixed_report | passed | mixed_report_bigbrain_tissuelink_visual_report_20261019T192528850824Z.html |
| Alignment review loaded | passed | http://127.0.0.1:8513/Validation |
| MRI alignment point | passed | Independent MRI point saved |
| histology alignment point | passed | Independent histology point saved and discrepancy displayed |

## Limitations

- Anatomical overlays remain awaiting independent review; the video does not claim anatomical accuracy.
- Any step marked failed or unavailable above is shown honestly and was not replaced with fabricated output.
- Downloaded files are demonstration artifacts under `demo/downloads/`; they are not changes to preserved source data.
- Chrome initiated the two manual-route collection downloads, but Playwright reported those two saves as canceled. Their controls and clicks are visible in the video. The later mixed ROI/manual self-contained HTML download completed and was saved successfully.

## Application inventory inspected before automation

- **MRI–Histology Explorer:** registered-section catalogue, coverage/evidence table, source metadata, alignment-to-section action, MRI and histology overview pickers, linked neighbourhood views, registered-section picker, patch size/resolution controls, optional atlas navigation, bounded patch fetch, statistics/review controls, collection controls, comparison tabs, diagnostics, saved locations, scientific ZIP and HTML exports, collection reopen/re-fetch, and advanced annotation/sampling controls.
- **Experimental template ROI:** preserved CerebrA example verification, explicit supported-template declaration, provenance, multi-file uploader, binary/grid validation, pinned-container transform, source/transformed overlays and downloads, placement inspection gate, section intersections, bounded ROI patch, collection integration, transform provenance, and ZIP/HTML collection controls.
- **Alignment review:** source/coordinate context, landmark candidate, independent MRI/histology point selection, slice/display controls, discrepancy table/metric, reviewer notes, and JSON export.
- Navigation contains exactly these three pages; no additional Streamlit application page was omitted.

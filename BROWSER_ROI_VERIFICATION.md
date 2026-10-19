# Experimental ROI browser verification

Date: 2026-10-19

Latest retry: 2026-10-19 11:24 America/Toronto

## Outcome

Browser verification is **incomplete because the shared browser-control
connection did not respond**. The application started successfully at
`http://127.0.0.1:8513/`, but `open`, `reload`, page-read and direct Playwright
requests all remained pending and had to be terminated. No browser-downloaded
ZIP was produced, and no programmatically generated ZIP is substituted for it.

On the latest retry, a read-only process check first confirmed that Streamlit
was not running. The unchanged app was restarted successfully and reported
`Uvicorn server started on 127.0.0.1:8513`. A subsequent reload through the
shared browser-control page still remained pending and had to be terminated.
The remaining blocker is therefore the browser-control channel, not an app
startup error.

Anatomical status remains **Anatomical placement awaiting independent
review**. A placement-confirmation checkbox is only a workflow gate and is not
an anatomical validation.

## Completed checks

- Updated the requested wording to **Load technically verified CerebrA
  example** and **Anatomical placement awaiting independent review**.
- The page explicitly states that uploads accept binary ROIs in the exact
  supported ICBM2009c nonlinear symmetric template, not arbitrary MRI scans.
- Added state invalidation so changing the selected intersecting section
  clears its stale patch preview/download state without changing the shared
  collection.
- Ran focused automated checks:

```text
15 passed in 1.30s
```

These checks cover checksum-gated loading of the preserved CerebrA input,
transformed output and patch, upload gating and validation, shared navigation,
and page startup. They do not replace the unfinished browser interaction and
download inspection below.

## Browser evidence not completed

The following requested evidence remains unfinished:

1. Browser screenshots of the source/transformed overlays.
2. Browser display of intersecting sections and selection of #3146.
3. Browser-triggered bounded patch fetch and visual overlap inspection.
4. Adding that patch to the browser-session collection.
5. Browser download of the collection ZIP.
6. Inspection of that actual downloaded ZIP, including manifest/file mapping,
   NIfTI geometry, annotation PNG mapping, ROI provenance and review status.
7. Browser proof that changing ROI/section clears stale state while preserving
   collected patches.

Consequently there is no downloaded ZIP path and no browser screenshots to
report at this checkpoint.

## Short manual checklist

1. Open `http://127.0.0.1:8513/` and choose **Experimental template ROI**.
2. Click **Load technically verified CerebrA example**. Confirm the success
   message says the historical transform was not repeated.
3. Inspect both overlays; record only visual plausibility and keep anatomical
   status awaiting review.
4. Tick the inspection gate and click **Compute intersecting available
   sections**.
5. Select **#3146**, fetch the bounded patch, and confirm overlap appears on
   the documented source plane.
6. Add the patch to the collection, download **Download collection ZIP**, and
   retain the exact browser download path.
7. Change the section, confirm the patch preview/download clears, then return
   to the collection and confirm its saved entry remains.
8. Share the downloaded ZIP or its path so its manifest, checksums, NIfTI and
   annotation mapping can be inspected without substituting another archive.

# Validation record

This record separates checks that were actually performed from checks that were not.
All retrievals used the local `.venv`, public data, and a 10 MiB `max_bytes` budget.

## Passed checks

### Direct siibra comparison

The exported default bundle was compared with a fresh direct `siibra` fetch using the same:

- section: `73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126` (#3458)
- source: `https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed`
- coordinate space: `bigbrain` / BigBrain microscopic template (histology)
- bounds: `[-20.0, -0.87, -20.0, -18.0, -0.85, -18.0]` mm, ordered as min x/y/z then max x/y/z
- requested resolution: `0.01` mm

Results from `outputs/direct_validation/direct_comparison.json`:

- raw arrays: `np.array_equal=True`, maximum absolute raw difference `0`
- shape: `(251, 2, 251)` in both images
- dtype and finite range: `uint8`, `0..255`
- actual voxel size: `[0.00800000038, 0.01999999955, 0.00800000038]` mm in both NIfTI reads
- affine: equal within `1e-6`; maximum absolute difference `4.7683715e-09` mm, caused by NIfTI float32 serialization versus the direct float64 provider affine
- raw NIfTI byte-content hash of the canonical reconstructed image: identical on both sides

The exact full-precision reproduction command copied from `metadata.json` was executed into `outputs/reproduction_command_check/`. Its output matched the UI export: shape equal, raw values `np.array_equal=True`, maximum absolute raw difference `0`, affine allclose within `1e-6`, and voxel sizes equal.

Software recorded by the comparison: Python 3.12.3, siibra 1.0.1-alpha.25, NumPy 2.5.4, nibabel 5.4.2, Streamlit 1.66.0.

### Selection path

Local geometry tests passed (`pytest -q`: 5 passed), including a flipped affine and zoomed/panned view round trip. The browser interaction test previously performed on the running app showed:

- an asymmetric dragged rectangle mapped all four display edges into source x/z bounds and populated the six numeric fields;
- zoom and horizontal pan preserved the same physical bounds after the stale-canvas bug was fixed;
- changing a numeric bound changed the displayed rectangle and invalidated the prior preview/confirmation;
- the default #3458 overview loaded, the exact crop preview succeeded, confirmation was required, and the ZIP download control was exercised;
- switching sections cleared the old crop and confirmation state.

The preserved asymmetric real-data example is x=`[-41.121199, -24.989489]`, y=`[-0.8695, -0.8495]`, z=`[-25.177701, -17.113701]` mm. Its independent bounded export is `outputs/asymmetric_demo/`, shape `(2017, 2, 1009)`, actual voxel size `[0.008, 0.020, 0.008]` mm. Its visualization was inspected and contains tissue architecture plus a recognizable large white fissure/background boundary. The export metadata records all four boundaries.

### Resolution handling

Both requests were bounded to the same 2 mm × 0.02 mm × 2 mm region:

| Requested | Returned shape | Returned voxel size | Uncompressed estimate |
|---|---:|---:|---:|
| 0.01 mm | `(251, 2, 251)` | `[0.008, 0.020, 0.008]` mm | 126,002 bytes |
| 0.1 mm | `(33, 2, 32)` | `[0.064, 0.020, 0.064]` mm | 2,112 bytes |

The app now requires an explicit checkbox acceptance before a coarser 0.1 mm preview can be requested. Requested resolution is never presented as the returned resolution; the returned provider voxel size is shown and placed in metadata.

### Export contents

`outputs/ui_export/bigbrain_cutout_bundle.zip` contains `bigbrain_crop.nii.gz`, `bigbrain_crop_preview.png`, and `metadata.json`. The scientific NIfTI opens with nibabel and has the validated shape, affine, and voxel sizes. The PNG is labelled as a visualization and uses contrast stretching only; raw uint8 values remain in NIfTI. Metadata includes section, source, coordinate space, requested and actual bounds/resolution, orientation, voxel-centre and edge conventions, software versions, retrieval date, license, checksum, and a full-precision reproduction command.

### Thickness representation

The two y samples are not duplicates. For the default crop, nonzero counts were `[0, 62827]` and means were `[0.0, 145.09]`; narrowing around the provider voxel centre returned one y sample with the same tissue data. The first plane is provider zero-filled padding, the second is tissue. No plane is squeezed or discarded.

Affine coordinates are voxel centres. The edge extent is half a voxel beyond the outer centre on each side. For the default crop, the preserved two-sample y centre range is `[-0.87, -0.85]` mm and the edge extent is approximately `[-0.88, -0.84]` mm.

## Failed checks

- The first direct comparison used exact affine equality and reported a false failure because the exported NIfTI stores affine values as float32 while the direct siibra object retained float64 values. The comparison was corrected to report the measured maximum difference and a documented `1e-6` tolerance; the raw arrays were already exactly equal.
- A later browser request for a larger asymmetric 60×120-pixel selection became slow against the public provider and was not counted as a completed browser export. The bounded asymmetric CLI export and the earlier successful browser asymmetric preview remain preserved.

## Unperformed checks

- No independent viewer check was performed. The NIfTI was opened with nibabel, not in ITK-SNAP, 3D Slicer, or another separate GUI viewer. Therefore landmark visibility in an independent viewer is not claimed as passed.
- No anatomical identity or neuroanatomical registration was validated. The landmark statement is limited to visual tissue architecture and a fissure/background boundary in the exported visualization.
- The app was not tested with every one of the 145 catalogued sections in the browser. Real bounded crops were validated from at least #47, #500, and #3458, with section-specific failures reported rather than substituted.

## Independent viewer instructions

Open `outputs/ui_export/bigbrain_crop.nii.gz` or the NIfTI extracted from another bundle in ITK-SNAP (`itksnap path/to/bigbrain_crop.nii.gz`) or 3D Slicer. Use the NIfTI world coordinates as the `bigbrain` / BigBrain microscopic template (histology) coordinate space; do not interpret them as patient MRI or MNI coordinates. The affine maps voxel centres in array x/y/z order, with y representing section thickness. Compare the displayed x/z location and bounds to `metadata.json`; the PNG is only a contrast-adjusted visualization. This procedure is documented for reproducibility but was not executed in an independent viewer in this validation run.

## Related-tool scope note

The previously cited Scout repository was an unrelated AI code-review
project and was not a BigBrain comparison. It has been removed from this
record. A public BigBrain-specific Scout repository could not be
verified from the public sources searched for this documentation update, so
this project makes no Scout overlap or novelty claim.

The verified upstream tools relevant to this project are
[siibra-python](https://github.com/FZJ-INM1-BDA/siibra-python), which supplies
BigBrain metadata and bounded provider access, and
[BigBrainWarp](https://github.com/caseypaquola/BigBrainWarp), which is a
separate external-MRI transformation project and is not required by the
current app. TissueLink is a local Streamlit patch-retrieval and collection
tool; similar interface elements are not evidence of unique functionality.

## Limitations

- Public provider availability and response behavior can change.
- The actual provider resolution may differ from the requested resolution; coarse requests require explicit acceptance in the app.
- A full section is never downloaded by the project, but the selected rectangle must still fit the configured 10 MiB request budget.
- Provider zero-filled thickness planes are preserved because they are part of the returned representation; users must inspect metadata before interpreting thickness.
- The preview applies a 1st–99th percentile linear contrast stretch for readability. Scientific exports are raw; preview appearance is not a quantitative intensity display.
- No region-name search or automatic registration is included.

Annotation-tool feasibility is documented separately in [ANNOTATION_INTEGRATION.md](ANNOTATION_INTEGRATION.md). It uses the existing crop only and does not change the validated downloader or exports.

## Integrated polygon annotation

Automated checks passed in `tests/test_polygon_annotations.py` for Fabric
polygon point normalization, scale/affine mapping, axis order, and annotated
ZIP contents. The complete suite was run as `pytest -q`: **15 passed**.

Browser-level checks passed on the local app for the preserved #3458 crop:

- preview succeeded with shape `(251, 2, 251)` and actual voxel size
  approximately `[0.008, 0.020, 0.008] mm`;
- confirmation was required before polygon tools appeared;
- an asymmetric four-vertex polygon was created on the crop canvas;
- its label was changed to `browser_landmark`;
- the app displayed both crop and section-overview polygon overlays;
- the mapped vertices stayed within the crop shape and used y-plane `1`;
- the annotated ZIP download control became available and produced
  `outputs/ui_annotation_export/bigbrain_cutout_bundle.zip`;
- the ZIP contained the scientific NIfTI, visualization PNG, metadata,
  `polygon_annotations.json`, and `polygon_mapping.json`;
- independent local inspection confirmed the exported label and all mapped
  voxel vertices were in bounds.

The browser test did not independently verify a human landmark identity; the
label is a user annotation only. Canvas editing/deletion controls are exposed
and the mapping helper has scale tests, but a separate browser drag-resize and
delete interaction was not completed in this run. The existing overview
zoom/pan mapping tests remain covered by `tests/test_geometry.py`; the crop
polygon canvas itself has no independent zoom control, so overview zoom/pan
only changes its display placement, not the exported physical vertices.

The Labelme import parser has automated checks for the existing mapping fixture, wrong-image checksum, wrong dimensions, unsupported shape type, non-finite vertices, and zoom/pan display remapping. A real polygon drawn and saved by the external Labelme GUI remains unperformed; the generated JSON fixture is not counted as that round trip.

## Patch collection milestone

### Atlas context versus patch membership

Ordinary manually selected patches do **not** receive automatic anatomical
region attribution. Their metadata contains
`patch_region_membership: "not established"` and, separately, an
`atlas_context` object naming the currently supported parcellation/region as
context only. This context is not a claim that the selected pixels belong to
that region, and user notes are not interpreted as anatomical labels.

The unresolved atlas mask-overlay work remains in the separate experimental
region-navigation diagnostics. It is not used to label manual patches and
does not change patch selection, raw values, affines, or collection export.
The nonzero-pixel and file-integrity checks in that diagnostic are numerical
checks only; they are not anatomical validation.

The new collection tests in `tests/test_patch_collection.py` use synthetic
byte fixtures labelled as sections `3458` and `3500`. They validate deterministic
IDs, duplicate rejection, removal, the 50 MiB budget, per-patch metadata,
manifest rows, and ZIP member names. They do **not** perform provider fetches
and do not prove that the browser UI collected two real sections.

Earlier catalogue tests did use real bounded siibra provider fetches for
sections including #3458, #3407, #3500 and #3556, but those tests exercised
the downloader/export path, not the new browser collection button.

No browser-downloaded collection ZIP was available for this validation run,
so manual collection observations, raw NIfTI comparison, and two-section
browser collection verification remain unperformed.

The collection's unmarked PNG is the display-only selected y plane transposed
for viewing at its native pixel dimensions; it has no crosshair, footprint,
orientation labels, scale bar, or display enlargement. Its intensity is the
existing 1st–99th percentile linear uint8 visualization conversion from
`display_plane`; the raw NIfTI values are unchanged. For a scientific array
in NIfTI `(x, y, z)` order, the canonical mapping is
`PNG[v,u] = data[u, selected_y, v]`: PNG columns are source X, PNG rows are
source Z, and pixel `(u,v)` maps to source voxel
`(u, selected_y, v)`. Applying the exported NIfTI affine to that voxel centre
gives its world coordinate. This PNG mapping is separate from the interactive
section-display mapping and is recorded explicitly in each patch metadata
file.

Historical note: earlier validation text described `(v, selected_y, u)` and
was superseded by the asymmetric-pixel regression. That convention is not
used by current exports.

## Selection synchronization follow-up

The detailed-section click and lower reconstruction marker previously used
separate visible state paths: the click was stored as a section-space point,
while the lower marker was rendered from the X/Y/Z widget values after the
rerun. The UI now reports the clicked section pixel, mapped world XYZ, lower
marker world XYZ, and next-fetch bounds together. A new detailed-section click
immediately invalidates the active patch and signature while preserving the
patch collection. The pure off-centre behavioral checks are in
`tests/test_selection_sync.py`.

The implementation now uses the detailed-section world point as the single
active point for the MRI marker, reconstructed-histology marker, whole-section
marker and next fetch bounds. The whole-section display is explicitly
horizontal world X / vertical world Z and is separate from the cropped
neighbourhood renderer. The non-square RGB overlay test exercises the actual
marker renderer and confirms that horizontal and vertical lines use display
`(u, v)` columns and rows.

The current automated run reports **51 passed**. Geometry, display and
collection tests include synthetic fixtures and are software checks, not
anatomical validation. Real provider checks are recorded separately below.

The browser interaction for this follow-up was not completed because the
shared browser connector did not return a usable page snapshot; visual marker
agreement remains pending manual confirmation.

### Patch collection status

Evidence is versioned by artifact and is not interchangeable:

| Artifact/version | Result |
| --- | --- |
| Earlier two-section browser ZIP | Independently inspected; both patch identities, manifest/file checksums and NIfTI geometry passed. This is historical evidence for that earlier download. |
| Later corrected one-section ZIP | Independently inspected for real #3458; corrected PNG mapping, dimensions, affine and checksum checks passed. |
| Latest browser #3458 run | Fetch and **Add patch to collection** were observed in the app. |
| Latest two-section browser collection download | Not completed; no claim is made for a current two-section browser ZIP. |

The current collection implementation preserves entries across section
changes within one Streamlit session, rejects duplicate IDs, enforces a 50 MiB
session budget, and exports raw NIfTI, an unmarked PNG plane, a marked preview,
per-patch metadata, a CSV manifest and a README. The unmarked PNG is a
visualization-only 1st–99th percentile conversion of the selected native
plane. For a source array in `(x, y, z)` order, its exact mapping is
`PNG[v,u] = data[u, y_slice, v]`; `y_slice`, dimensions, affine and checksums
are recorded in each patch metadata file.

The automated collection tests use synthetic byte fixtures labelled #3458 and
#3500. They verify collection bookkeeping and ZIP structure, not provider
fetches or anatomical correspondence. Real provider evidence exists for a
bounded #3458 detailed patch and bounded checks around #3500, but the browser
workflow that collects both sections and inspects its downloaded ZIP remains
incomplete. Manual observations and automated results must therefore remain
separate.

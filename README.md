# BigBrain TissueLink

BigBrain TissueLink is a local CLI and Streamlit interface for navigating
reference MRI and reconstructed BigBrain histology, inspecting one documented
registered detailed section, and retrieving bounded high-resolution tissue
patches with spatial metadata and provenance. This is public research data,
not patient MRI and not a clinical tool.

## Implemented scope

- Reference MRI/histology navigation using the single BigBrain donor and the
  documented final-histological-space reference volumes.
- One supported registered detailed section: **#3458**.
- Bounded detailed-patch retrieval with explicit request budgets, actual
  returned resolution, crop-adjusted affine and provenance export.
- Scientific NIfTI exports remain separate from contrast-adjusted visual
  reports; in-app polygon annotation and optional Labelme import remain
  available for the detailed crop workflow.
- Experimental reference-space placement is labelled **Not independently
  reviewed**. Matching coordinates do not establish exact anatomical
  correspondence.

The demonstrated detailed request is not “1 µm” simply because the source
collection is described that way: a `0.01 mm` request currently returns
approximately `[0.008, 0.020, 0.008] mm` from the public provider, with shape
`(251, 2, 251)` for the preserved default crop. The two thickness samples are
preserved, including the observed provider padding plane.

External participant-MRI upload is **not ready**. The exact ICBM2009c/ICBM2009sym
BigBrainWarp chain is documented in
[EXTERNAL_MRI_EXECUTION_REPORT.md](EXTERNAL_MRI_EXECUTION_REPORT.md), but the
isolated BigBrainWarp/MINC2 runtime has not completed locally. No automatic
registration is implemented.

## MRI–histology explorer status

The donor MRI feasibility audit is documented in [SPATIAL_MAPPING.md](SPATIAL_MAPPING.md). The official release provides a donor MRI in final histological processing space and native reconstructed histology volumes, but the current high-resolution siibra section provider does not expose a documented transform into that MRI, and the release warns that the MRI fit is not perfect. The linked MRI–histology migration is therefore intentionally stopped at reference-space inspection; the existing validated histology downloader and exports remain unchanged. The viewer synchronizes clicks only in the documented common reference coordinates; it does not perform anatomical registration or apply a guessed y–z flip.

An isolated volume-level inspection viewer is available for the official donor MRI and the native `full8_200um_optbal.nii.gz` volume only. It uses documented common world coordinates, keeps the two displayed voxel centres separate, and is labelled alignment inspection rather than validated anatomical correspondence:

```bash
.venv/bin/python volume_alignment.py --out outputs/spatial_feasibility/alignment_inspection
.venv/bin/streamlit run navigation.py --server.port 8504
```

The high-resolution siibra-section workflow remains separate and unlinked.
Its volume-level feasibility is documented in
[SECTION_VOLUME_MAPPING_FEASIBILITY.md](SECTION_VOLUME_MAPPING_FEASIBILITY.md);
that report does not change the interface or enable automatic annotation
placement.

The optional workflow `Explore registered detailed section #3458` is now
available in the app. It uses the documented provider geometry for a bounded
reference-space demonstration with the donor MRI and reconstructed 200 µm
volume. It reports the separately sampled slice centres, keeps the detailed
provider patch at its actual returned resolution, and marks the anatomical
status as **Not independently reviewed**. It does not create a registration,
claim exact MRI correspondence, or expose cellular-equivalent detail.
The local viewer URL is `http://127.0.0.1:8502/`. Its main page is a one-click
shared-coordinate explorer with display-only overlay opacity, RAS/voxel-size
metadata, an MRI sampling-voxel box, and an explicit notice that no documented
registration uncertainty radius is available. Independent MRI/histology point
pairs belong to the separate `Validation` page and remain `Unreviewed` until
both points are independently selected and saved. Their discrepancies are not
anatomical accuracy measurements.

Location reports distinguish two products. PNGs are **visual reports**: they
contain display contrast, orientation labels, scale bars, and a marked
selection, and must not be used as raw scientific data. The ZIP also contains
native-grid **scientific data exports**: one-voxel-thick MRI and reconstructed-
histology NIfTI crops with crop-adjusted affines, direct source values,
native voxel sizes, source/export checksums, and metadata. No interpolation or
resampled comparison volume is exported. Enlarging the 200 µm reconstruction
does not provide cellular detail.

The exact missing mapping that keeps detailed microscopy disabled is an
official transform or verified section-to-reconstructed-volume plane mapping
from the high-resolution siibra section provider into the donor MRI/native
histology volume. The volume viewer therefore must not be used to place
high-resolution section annotations in MRI. No disease map or corrected p-value
is bundled or shown; there is no project source supporting such a layer.

## Verified real-data milestone

Passed on 2026-10-18 with `siibra==1.0.1a25` (reported by the package as `1.0.1-alpha.25`). Selected source: section **#3458**, identifier `73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126`, a 1 micron cell-body-stained BigBrain scan. Source: [EBRAINS catalogue](https://search.kg.ebrains.eu/instances/73c1fa55-d099-4854-8cda-c9a403c6080a). Coordinate space is BigBrain microscopic template (histology), with x/y/z affine orientation supplied by siibra. The provider selected `[0.008, 0.020, 0.008] mm` for a `0.01 mm` request. The public dataset is distributed under BigBrain's CC BY-NC-SA 4.0 terms; check the source record for current attribution requirements.

The default tissue-containing CLI request is x/z `[-20, -18] mm`, full section thickness `y=[-0.87, -0.85] mm`, with a 10 MiB `max_bytes` cap. It returns a real uint8 NIfTI `(251, 2, 251)` with affine origin `(-20.0, -0.87, -20.0) mm`. The first y plane is provider zero-filled padding and the second contains the source section; both are preserved. The PNG applies a labelled 1st–99th percentile contrast stretch for visualization only; the scientific NIfTI retains original values. Export metadata records voxel-centre bounds, voxel-edge extent, and any observed provider zero-filled planes. A fresh full-precision reproduction matched the exported image pixel-for-pixel (`max_abs_diff=0`).

## Install and run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python bigbrain_cutout.py --out outputs/verified_patch
.venv/bin/streamlit run navigation.py --server.port 8504
```

The primary application URL is `http://127.0.0.1:8504/`. The legacy detailed
cutout page remains separately runnable with `.venv/bin/streamlit run app.py`.

For the current reference-volume inspection, use:

```bash
.venv/bin/streamlit run volume_viewer.py --server.port 8502
```

The app starts with the reference MRI/histology explorer. Choose the
registered-section workflow, navigate explicitly to section #3458, select a
bounded X/Z patch, preview it, confirm it, and download the package. A fresh
network retrieval is required for detailed data; existing local outputs are
not part of the public repository.

The CLI fails with an actionable error if the section, bounds, resolution, network, or memory/download budget cannot be satisfied. It never silently substitutes synthetic data or a coarser requested result. The exact output bundle is `outputs/verified_patch/bigbrain_cutout_bundle.zip` after a successful run.

## Tests and limitations

`pytest -q` covers local bound validation and the explicit budget. The direct exported-image comparison, bounded multi-resolution checks, browser path checks, and unperformed independent-viewer checks are separated in [VALIDATION.md](VALIDATION.md). Browser smoke testing was executed locally: overview loaded, a rectangle was dragged, all four edges mapped to source coordinates and populated the six numeric fields, a crop preview succeeded, confirmation enabled the bundle action, and the ZIP download control was exercised. Switching from #3458 to #47 cleared the old crop and confirmation and loaded #47 metadata/overview. Coarser requests require an explicit acceptance checkbox before preview retrieval.

siibra functionality reused: configured `CellbodyStainedSection`, `BoundingBox`, bounded `fetch`, provider-selected resolution, NIfTI affine/header. This project adds strict bounds/budget handling, scientific/visual export separation, provenance JSON, checksum, ZIP bundling, and a small confirmation UI. It deliberately does not add region search or registration.

Issue review: [#704](https://github.com/FZJ-INM1-BDA/siibra-python/issues/704) reports an old `Volume.intersection()` ROI problem; this project avoids that path by validating against `get_boundingbox(clip=False)` and passing an explicit bounded `voi`. [#705](https://github.com/FZJ-INM1-BDA/siibra-python/issues/705) was reviewed as a reported fetch/ROI concern. [#706](https://github.com/FZJ-INM1-BDA/siibra-python/issues/706) reports import-time `SIIBRA_MAX_FETCH_SIZE_BYTES` behavior and old warning behavior; this project sets the variable before importing siibra and also passes `max_bytes` explicitly. These issue reports are not treated as proof of current-version behavior.

Potential overlap with the current public [Scout README](https://github.com/esreekarreddy/scout/blob/main/README.md) and relevant implementation is assessed in [VALIDATION.md](VALIDATION.md). This project makes no novelty claim; its scope is a verified local crop/export workflow.

## Credits and data terms

This project reuses [siibra-python](https://github.com/FZJ-INM1-BDA/siibra-python)
for configured BigBrain section metadata, bounded provider fetches and NIfTI
geometry; [BigBrainWarp](https://github.com/caseypaquola/BigBrainWarp) is
documented as the external MRI-transform dependency but is not required for
the current app; and the [BigBrain Project](https://bigbrainproject.org/) is
the source of the donor MRI, reconstructed histology and detailed section
data. Related projects and limitations are described in the validation
documents. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for software
licenses and keep BigBrain data terms separate from this code license.

## Feedback

Use the repository's [bug report template](.github/ISSUE_TEMPLATE/bug_report.md)
for reproducible software issues. Do not upload patient data, credentials or
unlicensed images to an issue.

## Current export and section metadata findings

The provider metadata for each selected section reports a precomputed volume of size `[..., 1, ...]` along the thickness axis, with `20,000 nm` (`0.020 mm`) resolution. A request using the full configured section y bounds can return two y samples because siibra's Neuroglancer reader computes `ceil(max)-floor(min)` in voxel coordinates and zero-fills the part outside the one-sample source. For section #3458, the two planes were not duplicates: the returned `(251, 2, 251)` crop had nonzero counts `[0, 62827]` and means `[0.0, 145.09]`. Narrowing the request around the provider voxel center, for example `y=[-0.86,-0.85]`, returned `(251, 1, 251)` with nonzero count `62827`. The project preserves both samples in the scientific export and records the padding observation rather than squeezing it.

NIfTI affine coordinates are voxel centres. Physical voxel edges extend half a voxel beyond the first and last centre. For the preserved default crop, the requested y centres are `-0.87` and `-0.85 mm`; the centre-to-centre extent is `0.02 mm`, while the two-sample voxel-edge extent is `0.04 mm`. This distinction is shown in technical metadata where relevant.

The app now queries 145 public section records before image retrieval. Each record exposes identifier, source precomputed URL, BigBrain histology coordinate-space bounds, and eight provider scales from approximately `0.001` to `0.128 mm` in x/z (`0.020 mm` through thickness). Real bounded crops were validated from #47, #500, and the preserved #3458 section. The app uses the low-resolution `0.128 mm` overview under a 5 MiB cap and the selected section’s own metadata; it does not download all images.

Rectangle selection uses `streamlit-drawable-canvas`. Its four display edges are mapped through the overview affine and display scale into source x/z bounds, with y set to the selected section thickness. Numeric source bounds remain available under Advanced settings. Changing section or crop parameters clears the crop and confirmation state.

The selection is stored in source coordinates, not canvas pixels. The overview supports independent zoom, horizontal pan, vertical pan, and reset-view controls; changing those controls does not remap the selected bounds. Numeric edits update the displayed rectangle, and a new rectangle updates all six numeric fields. The crop preview is shown before confirmation, with its x/z physical aspect ratio preserved and the same rectangle overlaid on the overview. Any selection or resolution change invalidates the previous preview and export confirmation.

An asymmetric demonstration rectangle was mapped in the browser as x=`[-41.121199, -24.989489]`, y=`[-0.8695, -0.8495]`, z=`[-25.177701, -17.113701]` mm, corresponding to 60×120 display pixels. Its independent CLI export is in `outputs/asymmetric_demo/`; the visualization shows recognizable tissue architecture and a large white fissure/background boundary. The export has shape `(2017, 2, 1009)`, actual voxel size `[0.008, 0.020, 0.008] mm`, and the metadata records all four physical boundaries.

The default UI example remains the validated #3458 tissue crop above. The overview is requested at `0.128 mm` under a 5 MiB cap; the provider reports the actual voxel size (currently approximately `[0.128, 0.020, 0.128] mm`). Crop requests at `0.01 mm` currently resolve to approximately `[0.008, 0.020, 0.008] mm`; requested and actual resolution are shown separately.

## In-app polygon workflow

After a successful crop preview, check the confirmation box, then use the
integrated polygon canvas on the confirmed patch. Click polygon vertices and
double-click the first vertex to close it. Use the canvas **Edit** control to
move or resize a polygon and **Delete selected** to remove it. Draw multiple
polygons; each receives an editable name below the canvas. The crop and
section-overview overlays are recomputed from the same physical vertices.

The canvas uses the displayed crop image only for visualization. Its pixel
coordinates are mapped through the crop affine to `(i_x, i_y, i_z)` with the
selected y-plane, and the raw NIfTI remains unchanged. Changing section,
bounds, or resolution clears polygons and invalidates prior results. The
annotated bundle is written to `outputs/ui_annotation_export/` and contains
the scientific NIfTI, visualization PNG, base metadata, `polygon_annotations.json`,
and `polygon_mapping.json`. The original validated bundle in
`outputs/ui_export/` is kept separate.

Labelme import remains optional under the advanced section and is not needed
for the main workflow. No automatic segmentation, registration, or anatomical
label prediction is performed.

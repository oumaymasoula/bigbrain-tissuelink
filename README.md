# BigBrain TissueLink

BigBrain TissueLink is a local research tool for exploring the public BigBrain donor MRI alongside reconstructed histology. It helps a researcher navigate to one documented registered section, inspect a bounded detailed tissue patch, and export the image with spatial metadata and provenance.

## Workflow

```text
reference MRI → registered histology section → patch selection → export
```

The workflow uses reference data from one donor. It is for spatial inspection, not patient MRI, diagnosis, registration, or anatomical validation.

## Status

| Available now | Not included yet |
| --- | --- |
| Donor MRI and reconstructed histology navigation | Arbitrary participant-MRI upload |
| 145 metadata-discovered registered sections; demonstrated detailed workflow for **#3458** | Automatic registration |
| Bounded patch retrieval with request limits | Cellular-resolution claims from the 200 µm volume |
| Native scientific NIfTI plus visual PNG and JSON provenance | Anatomically validated correspondence |
| Optional in-app polygon annotation and Legacy/Labelme import | Region-name search or segmentation |

The displayed reference volumes are MRI at approximately **0.444 mm** and reconstructed histology at **200 µm**; the latter does not resolve individual cells. A verified #3458 detailed request asks for `0.01 mm` and the preserved collection export returns `[0.008, 0.020, 0.008] mm` with shape `(251, 1, 251)`. Provider thickness/padding can vary by request; requested and actual resolutions are always recorded separately in the app and export metadata.

The detailed section is placed using documented reference-space provider geometry and remains **Not independently reviewed** anatomically. The two y samples in the preserved default crop are retained because the provider returns one source plane plus a zero-filled padding plane; they are not silently squeezed.

After fetching a detailed patch, **Add patch to collection** saves it in the
current browser session with a deterministic patch ID, optional user label and
note, section identity, bounds, affine, actual resolution and checksums.
Collection export contains each raw NIfTI, an unmarked PNG plane for external
annotation, a separate marked preview, per-patch metadata, `manifest.csv` and
a README. The collection is capped at 50 MiB and is not persistent across a
browser refresh; download the ZIP to retain it.

## Install and launch

From the project directory:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run the bounded real-data CLI example:

```bash
.venv/bin/python bigbrain_cutout.py --out outputs/verified_patch
```

Start the primary app:

```bash
.venv/bin/streamlit run navigation.py --server.port 8513
```

Open <http://127.0.0.1:8513/>. The current entry point is `navigation.py`; choose the MRI–Histology Explorer, select a registered section, confirm the reference plane, choose an X/Z location, fetch the bounded patch, inspect it, and download the package.

The app needs the local feasibility volumes at:

```text
outputs/spatial_feasibility/mri_to_blk_aligned.nii.gz
outputs/spatial_feasibility/full8_200um_optbal.nii.gz
```

### Reference-volume setup

These are the exact public BigBrain Release 2015 files used by the paired
viewer. Download them only when needed; they are large and are not included
in Git:

```bash
mkdir -p outputs/spatial_feasibility
curl -L --fail --retry 3 \
  https://ftp.bigbrainproject.org/bigbrain-ftp/BigBrainRelease.2015/3D_MRI/nii/mri_to_blk_aligned.nii.gz \
  -o outputs/spatial_feasibility/mri_to_blk_aligned.nii.gz
curl -L --fail --retry 3 \
  https://ftp.bigbrainproject.org/bigbrain-ftp/BigBrainRelease.2015/3D_Volumes/Histological_Space/nii/full8_200um_optbal.nii.gz \
  -o outputs/spatial_feasibility/full8_200um_optbal.nii.gz
```

Verify that the files are the expected NIfTI volumes before launching:

```bash
.venv/bin/python - <<'PY'
import nibabel as nib
from pathlib import Path
expected = {
    "mri_to_blk_aligned.nii.gz": ((315, 362, 284), (0.44444445, 0.44444445, 0.44444445)),
    "full8_200um_optbal.nii.gz": ((696, 770, 605), (0.2, 0.2, 0.2)),
}
root = Path("outputs/spatial_feasibility")
for name, (shape, zooms) in expected.items():
    image = nib.load(root / name)
    actual_zooms = tuple(round(float(v), 7) for v in image.header.get_zooms()[:3])
    assert tuple(image.shape[:3]) == shape, (name, image.shape)
    assert actual_zooms == tuple(round(v, 7) for v in zooms), (name, actual_zooms)
    print(name, "OK", image.shape[:3], actual_zooms)
PY
```

The URLs, headers, processing-space evidence and licensing caveats are
documented in [SPATIAL_MAPPING.md](SPATIAL_MAPPING.md). File sizes and
checksums can vary only if the upstream release changes; record
`sha256sum` output locally when mirroring these files.

The volume-level inspection can be run separately:

```bash
.venv/bin/streamlit run volume_viewer.py --server.port 8502
```

The legacy detailed-cutout page remains separately runnable:

```bash
.venv/bin/streamlit run app.py
```

The CLI and app fail with an actionable error when source data, bounds, resolution, network access, or the request budget cannot satisfy the request. They do not substitute synthetic data or an unrequested coarser result.

## Exports

The detailed-section ZIP contains raw native-grid NIfTI data, a visualization PNG, a footprint visualization, and JSON metadata. The scientific image preserves source values and its crop-adjusted affine; the PNG is a contrast-adjusted visual report. Metadata records section identity, provider URL, coordinate space, requested and actual bounds/resolution, sampled centres, transform/provenance fields, and checksums.

Location reports similarly separate visual PNGs from native-grid MRI and reconstructed-histology NIfTI neighbourhoods. Polygon exports preserve image-pixel vertices and their mapping provenance. No interpolation is used in scientific crops.

## Validation and scope

The documented real-data milestone, provider issue review, section metadata audit, coordinate conventions, overlap checks, export checks, and browser checks are recorded in [VALIDATION.md](VALIDATION.md). The multi-section catalogue and bounded-fetch verification are in [SECTION_CATALOGUE_VALIDATION.md](SECTION_CATALOGUE_VALIDATION.md). Reference-volume mapping and limitations are in [SPATIAL_MAPPING.md](SPATIAL_MAPPING.md); the registered-section feasibility evidence is in [SECTION_VOLUME_MAPPING_FEASIBILITY.md](SECTION_VOLUME_MAPPING_FEASIBILITY.md). The external MRI execution status is in [EXTERNAL_MRI_EXECUTION_REPORT.md](EXTERNAL_MRI_EXECUTION_REPORT.md).

The viewer uses documented final-histological-space reference coordinates. Matching world coordinates do not guarantee matching anatomy, and no guessed flip, new registration, uncertainty estimate, or cellular-equivalence claim is applied. External participant-MRI upload is not ready because the exact ICBM2009c/BigBrainWarp execution chain has not completed locally.

## Current verification status

- Automated suite: **50 tests passed** in the latest run. The geometry,
  collection and renderer regressions use synthetic fixtures; they do not
  replace anatomical review.
- Real provider evidence includes bounded detailed retrieval for #3458 and
  bounded metadata/mask checks for #3500. The corrected local collection
  export currently contains one real #3458 patch; it is not a two-section
  browser collection.
- Initial browser inspection observed section #3458 synchronization to its
  documented plane near `Y=-0.8595 mm`; the MRI and 200 µm views reported
  separately sampled slice centres. The current browser run did not complete
  the full two-section click → fetch → collection-download sequence.
- A browser-downloaded ZIP from that sequence was not available for this
  checkpoint. Consequently, browser confirmation of #3458 and #3500 as two
  collected entries remains unperformed. Do not interpret file-integrity
  checks or provider-array equality as anatomical validation.

For a repeatable local fallback, inspect the previously verified real-data
outputs under `outputs/collection_regenerated/` or `outputs/verified_patch/`.
Those files are intentionally excluded from Git and are not a substitute for
running the provider workflow.

The verified detailed source is the [EBRAINS record for section #3458](https://search.kg.ebrains.eu/instances/73c1fa55-d099-4854-8cda-c9a403c6080a). The earlier siibra reports [#704](https://github.com/FZJ-INM1-BDA/siibra-python/issues/704), [#705](https://github.com/FZJ-INM1-BDA/siibra-python/issues/705), and [#706](https://github.com/FZJ-INM1-BDA/siibra-python/issues/706) are documented as historical issue reports, not assumptions about current behaviour.

## Reused software and attribution

The project reuses [siibra-python](https://github.com/FZJ-INM1-BDA/siibra-python) for BigBrain section metadata, bounded provider fetches, and NIfTI geometry. [BigBrainWarp](https://github.com/caseypaquola/BigBrainWarp) is documented as a separate external MRI-transform dependency and is not required for the current app. Data come from the [BigBrain Project](https://bigbrainproject.org/). Related-project overlap, including Scout, is discussed in [VALIDATION.md](VALIDATION.md); this project makes no interface-based novelty claim.

BigBrain data terms and attribution requirements are separate from the MIT license for original project code. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [LICENSE](LICENSE). Use the [bug-report template](.github/ISSUE_TEMPLATE/bug_report.md) for reproducible software issues; do not upload patient data, credentials, or unlicensed images.

## Planned extensions

Future work may add a completed, verified external-MRI transform chain and additional registered sections. Those extensions require documented transforms and independent anatomical review; they are not part of the current implementation.

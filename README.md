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
| Registered detailed section **#3458** | Automatic registration |
| Bounded patch retrieval with request limits | Cellular-resolution claims from the 200 µm volume |
| Native scientific NIfTI plus visual PNG and JSON provenance | Anatomically validated correspondence |
| Optional in-app polygon annotation and Legacy/Labelme import | Region-name search or segmentation |

The displayed reference volumes are MRI at approximately **0.444 mm** and reconstructed histology at **200 µm**; the latter does not resolve individual cells. The demonstrated #3458 detailed request asks for `0.01 mm` and currently returns approximately `[0.008, 0.020, 0.008] mm` with shape `(251, 2, 251)`. Requested and actual resolutions are shown separately in the app and export metadata.

The detailed section is placed using documented reference-space provider geometry and remains **Not independently reviewed** anatomically. The two y samples in the preserved default crop are retained because the provider returns one source plane plus a zero-filled padding plane; they are not silently squeezed.

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
.venv/bin/streamlit run navigation.py --server.port 8504
```

Open <http://127.0.0.1:8504/>. Choose the MRI–Histology Explorer, activate **Explore registered detailed section #3458**, select an X/Z location, fetch the bounded patch, inspect it, and download the package.

The app needs the local feasibility volumes at:

```text
outputs/spatial_feasibility/mri_to_blk_aligned.nii.gz
outputs/spatial_feasibility/full8_200um_optbal.nii.gz
```

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

The documented real-data milestone, provider issue review, section metadata audit, coordinate conventions, overlap checks, export checks, and browser checks are recorded in [VALIDATION.md](VALIDATION.md). Reference-volume mapping and limitations are in [SPATIAL_MAPPING.md](SPATIAL_MAPPING.md); the registered-section feasibility evidence is in [SECTION_VOLUME_MAPPING_FEASIBILITY.md](SECTION_VOLUME_MAPPING_FEASIBILITY.md). The external MRI execution status is in [EXTERNAL_MRI_EXECUTION_REPORT.md](EXTERNAL_MRI_EXECUTION_REPORT.md).

The viewer uses documented final-histological-space reference coordinates. Matching world coordinates do not guarantee matching anatomy, and no guessed flip, new registration, uncertainty estimate, or cellular-equivalence claim is applied. External participant-MRI upload is not ready because the exact ICBM2009c/BigBrainWarp execution chain has not completed locally.

The verified detailed source is the [EBRAINS record for section #3458](https://search.kg.ebrains.eu/instances/73c1fa55-d099-4854-8cda-c9a403c6080a). The earlier siibra reports [#704](https://github.com/FZJ-INM1-BDA/siibra-python/issues/704), [#705](https://github.com/FZJ-INM1-BDA/siibra-python/issues/705), and [#706](https://github.com/FZJ-INM1-BDA/siibra-python/issues/706) are documented as historical issue reports, not assumptions about current behaviour.

## Reused software and attribution

The project reuses [siibra-python](https://github.com/FZJ-INM1-BDA/siibra-python) for BigBrain section metadata, bounded provider fetches, and NIfTI geometry. [BigBrainWarp](https://github.com/caseypaquola/BigBrainWarp) is documented as a separate external MRI-transform dependency and is not required for the current app. Data come from the [BigBrain Project](https://bigbrainproject.org/). Related-project overlap, including Scout, is discussed in [VALIDATION.md](VALIDATION.md); this project makes no interface-based novelty claim.

BigBrain data terms and attribution requirements are separate from the MIT license for original project code. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [LICENSE](LICENSE). Use the [bug-report template](.github/ISSUE_TEMPLATE/bug_report.md) for reproducible software issues; do not upload patient data, credentials, or unlicensed images.

## Planned extensions

Future work may add a completed, verified external-MRI transform chain and additional registered sections. Those extensions require documented transforms and independent anatomical review; they are not part of the current implementation.

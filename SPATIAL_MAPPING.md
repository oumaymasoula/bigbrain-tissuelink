# MRI–histology spatial mapping feasibility

Status: feasibility report only. The existing BigBrain TissueLink downloader and
its validated exports remain the active application. No MRI–histology page or
coordinate service has been added because the complete mapping required for
the high-resolution section provider has not been established.

## Sources inspected

- Donor MRI: [official `mri_to_blk_aligned.nii.gz`](https://ftp.bigbrainproject.org/bigbrain-ftp/BigBrainRelease.2015/3D_MRI/nii/mri_to_blk_aligned.nii.gz).
- Official context and acquisition history: [BigBrain project overview](https://bigbrainproject.org/about.html).
- Release inventory and processing notes: [BigBrain Release 2015 `Updates.txt`](https://ftp.bigbrainproject.org/bigbrain-ftp/BigBrainRelease.2015/Updates.txt).
- Reconstructed volumes: [native histological-space NIfTI directory](https://ftp.bigbrainproject.org/bigbrain-ftp/BigBrainRelease.2015/3D_Volumes/Histological_Space/nii/).
- Published transforms: [MNI-ICBM152 transformation directory](https://ftp.bigbrainproject.org/bigbrain-ftp/BigBrainRelease.2015/3D_Volumes/MNI-ICBM152_Space/transformation/).
- Upstream volume-warp implementation/docs inspected: [BigBrainWarp transformation scripts](https://github.com/caseypaquola/BigBrainWarp/blob/master/docs/pages/scripts.rst).
- Installed implementation tested: [`siibra==1.0.1a25`](https://github.com/FZJ-INM1-BDA/siibra-python), specifically its `CellbodyStainedSection` and image-provider code in the project `.venv`.

The official overview says that the corrected sections were nonlinearly
registered to the postmortem MRI and reassembled into a 20 µm model. The
release notes add that the MRI in `3D_MRI` is in the final histological space
and should be used for comparison with the histological-space volumes; they
also explicitly warn that it does not fit perfectly. The FAQ separately says
the MRI is a fixed, skull-removed brain and that its processing-space axes
have a y–z flip. That FAQ statement is not used as an unverified transform.

The exact release-note wording is:

> “3D_MRI : added the MRI of BigBrain in the final histological space. Use
> this MRI to compare to the volumes in 3D_Volumes”

The same note continues by warning that the fit is imperfect and that the
Raw_Data MRI must not be used for comparison with the aligned volumes.

Source: [BigBrain Release 2015 `Updates.txt`](https://ftp.bigbrainproject.org/bigbrain-ftp/BigBrainRelease.2015/Updates.txt), lines 99–104.

## Source and target spaces

| Name | Role | Units | Axis/header evidence | Provenance and limitation |
|---|---|---|---|---|
| `bigbrain` / BigBrain microscopic template (histology) | Existing high-resolution 2D section provider and exported crop | mm in project metadata | siibra section bboxes and fetched NIfTI affine; existing crop uses array `(x,y,z)` and `y` as section thickness | Provider metadata identifies the space, but does not publish a transform from an individual 2D section/provider tile to the donor MRI header. |
| BigBrain native histological space | Manageable reconstructed volume candidate | mm | Official native volume `full8_200um_optbal.nii.gz` header inspected locally | This is the documented comparison space for the final-histological-space MRI. It is not a substitute for proving the high-resolution provider linkage. |
| donor MRI `mri_to_blk_aligned` | Reference MRI target | mm | Official NIfTI header inspected locally; `sform_code=1`, `qform_code=0`, orientation `RAS` | Fixed postmortem MRI in processing/final histological space; official release says the fit to histology is not perfect. It is not labelled T1-weighted because the inspected source does not verify that acquisition label. |
| MNI-ICBM152 2009b | Separate standard-space target | mm | Official `bigbrain_to_icbm2009b_lin.xfm`, `bigbrain_to_icbm2009b_nl.xfm`, and nonlinear grid | This is a published BigBrain/histology-to-MNI mapping, not a donor-MRI mapping and not an identity transform for the app. |

## Measured headers

The following files were downloaded from the official FTP and inspected with
NiBabel 5.4.2. Their local copies are retained under
`outputs/spatial_feasibility/` for reproducibility.

| File | Shape | Voxel size | Affine translation | Orientation |
|---|---:|---:|---:|---|
| `mri_to_blk_aligned.nii.gz` | `(315, 362, 284)` | `(0.44444445, 0.44444445, 0.44444445)` mm | `(-70.666603, -71.570000, -58.777699)` mm | `RAS` |
| `full8_200um_optbal.nii.gz` | `(696, 770, 605)` | `(0.2, 0.2, 0.2)` mm | `(-70.666603, -72.910004, -58.777699)` mm | `RAS` |

The similar x/z origins and axis codes are useful evidence that the release
intends these volumes to be compared in a common final histological frame.
They are not, by themselves, proof of voxelwise anatomical identity. The
different y origin, different resolution, and the official “does not fit
perfectly” warning make a blind index or identity mapping inappropriate.

The donor MRI file has SHA-256
`2d930b8454d22dd1bb9d7bb33935f4e22e465638d95d8beb87356350920b0f43`.
The inspected native histology file has SHA-256
`69f19eb044d23a09c0c316e8ce985fcd6822914d19ac0ec36e72aa8e03026bef`.

## Candidate transforms and direction

The official FTP exposes:

- `bigbrain_to_icbm2009b_lin.xfm`: a linear transform from BigBrain to
  ICBM2009b;
- `bigbrain_to_icbm2009b_nl.xfm`: a nonlinear grid transform whose file
  explicitly references the preceding linear transform;
- `bigbrain_to_icbm2009b_nl_grid_0.mnc`: the corresponding displacement grid.

These are suitable evidence that a BigBrain-to-MNI mapping exists, with the
linear transform applied before the nonlinear transform. They do not provide
the inverse or forward transform needed to map an arbitrary high-resolution
siibra section point to the donor MRI. The separate BigBrainWarp README
documents surface spherical maps to/from CIVET MNI152, also not a volumetric
donor-MRI transform.

The project therefore has no implemented transform direction between:

```text
high-resolution siibra section/provider (`bigbrain`)
    ↔ donor MRI (`mri_to_blk_aligned`)
```

and no validated inverse. I will not infer it from the FAQ y–z wording,
matching affine components, section filenames, or equal-looking dimensions.

For the two official volumes only, the release note is explicit enough to
support using their NIfTI world coordinates as a common **reference frame for
inspection**. It does not support treating every equal world coordinate as a
validated anatomical correspondence. The separate experimental viewer uses
only these two volumes, samples each at the requested world plane, tracks the
actual voxel centre selected in each volume, and displays the result as
“alignment inspection”.

## Relationship to the existing detailed-section provider

The existing downloader uses siibra `CellbodyStainedSection`, an explicit
`bigbrain` bounding box, the provider’s precomputed section URL, and the
provider-selected affine/resolution. This establishes a reproducible mapping
from crop array indices to the section provider’s own histology coordinates;
see [`bigbrain_cutout.py`](./bigbrain_cutout.py) and
[`VALIDATION.md`](./VALIDATION.md).

The official release notes establish that the reconstructed native volume and
`3D_MRI` are intended to share final histological processing space. They do
not state that the current 1 µm provider’s 2D tiles have the same voxel
origin, section-index convention, or registration residuals as the native
volume header, and the siibra section provider metadata inspected here does
not expose a donor-MRI transform. Consequently, connecting a detailed crop
to MRI is not yet a complete documented mapping.

## Decision and next evidence required

The volume-level experiment is supported as a documented world-coordinate
inspection. The current app remains a separate histology-only retrieval and
annotation tool. No identity mapping, guessed flip, MNI substitution, or
registration has been added. The experimental viewer does not connect to the
high-resolution siibra section provider.

To proceed safely, one of the following must be obtained and independently
validated:

1. an official transform or documented shared-coordinate contract from the
   current high-resolution section provider to the donor MRI/final
   histological volume; or
2. a documented method for matching a provider section to the corresponding
   reconstructed-volume plane, plus a verified point/plane transform and
   manual review of at least three landmarks in both modalities.

Until then, numerical affine round trips would only test arithmetic, not
anatomical alignment. MRI click synchronization, histology-to-MRI polygon
placement, landmark validation, and browser-level linked-navigation tests are
therefore remain unperformed for high-resolution sections.

## Three expert landmark checks

These are review targets, not asserted anatomical labels. They use the
common-world inspection grid at `y=-25.7922 mm` and must be checked by an
expert in both the MRI and native-histology panels:

1. `P1` — midline superior structure candidate: `(x=0.0, y=-25.7922,
   z=45.0) mm`; check that the central outline and midline relationship are
   qualitatively comparable without interpreting residual differences as
   registration error estimates.
2. `P2` — midline deep-structure candidate: `(x=0.0, y=-25.7922,
   z=0.0) mm`; check the central cleft/ventricular-looking feature and the
   left/right symmetry context.
3. `P3` — asymmetric lateral cortical candidate: `(x=-32.0, y=-25.7922,
   z=-12.0) mm`; compare the selected outer cortical boundary and nearby
   sulcal pattern against the corresponding world-coordinate view.

The coordinates specify displayed world points only. They do not prove that
the candidate feature is the named anatomy, and they do not provide an
uncertainty radius. Expert review is still required.

Generate the inspection images with:

```bash
.venv/bin/python volume_alignment.py --out outputs/spatial_feasibility/alignment_inspection
```

Run the isolated viewer with:

```bash
.venv/bin/streamlit run volume_viewer.py --server.port 8502
```

The generated outputs are [volume_side_by_side.png](outputs/spatial_feasibility/alignment_inspection/volume_side_by_side.png), [volume_world_overlay.png](outputs/spatial_feasibility/alignment_inspection/volume_world_overlay.png), and [alignment_inspection.json](outputs/spatial_feasibility/alignment_inspection/alignment_inspection.json). Display contrast is visualization-only and does not alter source values.

The viewer also exposes synchronized world-coordinate crosshairs, a
display-only overlay-opacity slider, RAS orientation and voxel-size metadata,
and separate requested coordinates versus the actual voxel centre selected by
each affine. Reviewers can enter MRI and histology points independently for
ten candidate rows and export the independent point-pair JSON from the separate
`Validation` page. Each reported distance is a **landmark discrepancy**, not a
whole-brain accuracy score; rows remain `Unreviewed` until both points are
independently selected and saved.

Candidate screenshot packages are under
`outputs/spatial_feasibility/landmark_review/` with manifest
`landmark_review_manifest.json`. They are labelled review candidates and are
not verified anatomical matches.

The corrected numerical validation record is
`outputs/spatial_feasibility/landmark_review/validation_log.json`: the
displayed points `(-1,-45,35) mm` and `(1,-45,35) mm` are separated by
`2.0 mm`, not 1 mm. This remains a numerical check only; P1/P2/P3 and this
pair are shown as **Unreviewed** until a reviewer independently selects and
saves corresponding points in both modalities.

## License and attribution

The official project page states the donor and acquisition context and links
the BigBrain publications. The existing app records the dataset’s
CC BY-NC-SA 4.0 attribution requirement from its source record. The official
website footer separately licenses website images under CC BY-SA; that website
license should not be silently applied to the downloaded volume data. Any
future linked view must retain the source URL, citation, license terms, and
the distinction between reference anatomy and patient imaging.

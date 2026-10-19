# ROI-to-patch feasibility test

This is a separate diagnostic milestone. It does not change the Streamlit
workflow, perform MRI registration, or claim anatomical correctness.

## Stage 1 — BigBrain-space extraction

Status: **passed bounded extraction and affine-overlap checks**.

The starting point is the preserved real-data exact-plane audit for section
`#3458`, not a coordinate inferred from a section number. The selected
nonzero provider voxel was:

```text
(-38.56517693785311, -0.8594999999999994, 9.204207252302027) mm
```

The test created a binary extraction ROI with shape `(20, 2, 20)` in
`(x, y, z)` order and this explicit affine (millimetres):

```text
[[0.20, 0.00, 0.00, -40.00],
 [0.00, 0.02, 0.00,  -0.8695],
 [0.00, 0.00, 0.20,  8.00],
 [0.00, 0.00, 0.00,  1.00]]
```

The ROI world bounds are `x=-40..-36.2`, `y=-0.8695..-0.8495`,
`z=8..11.8` mm. Catalogue bounds identified only section `#3458` as an
intersection candidate. This is a plane/bounds candidate, not anatomical
evidence.

A bounded real provider fetch then used:

```text
section: #3458
provider: https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed
requested bounds:
(-39.56517693785311, -0.8994999999999994, 8.204207252302027)
to
(-37.56517693785311, -0.8194999999999993, 10.204207252302027) mm
requested resolution: 0.01 mm
returned shape: (251, 5, 251) xyz
returned voxel size: approximately (0.008, 0.020, 0.008) mm
sampled provider slice: y index 2, centre Y=-0.8594999999999994 mm
```

ROI values were sampled at the fetched patch voxel centres using the full
inverse ROI affine and nearest-neighbour categorical sampling. The sampled
ROI plane was then intersected with provider values other than the declared
background value `255`. The result was **13,659 non-background overlapping
voxels**. This validates extraction geometry and array overlap only; it is not
MRI-to-BigBrain registration or anatomical validation.

Outputs:

- [stage1_binary_roi.nii.gz](outputs/roi_patch_feasibility/stage1_binary_roi.nii.gz)
- [stage1_patch.nii.gz](outputs/roi_patch_feasibility/stage1_patch.nii.gz)
- [stage1_roi_patch_overlay.png](outputs/roi_patch_feasibility/stage1_roi_patch_overlay.png)
- [stage1_metadata.json](outputs/roi_patch_feasibility/stage1_metadata.json)

Reproduce with:

```bash
cd /path/to/bigbrain-tissuelink
./.venv/bin/python roi_patch_feasibility.py
```

The overlay is display-only: `patch[:, y, :].T`, horizontal source `z`,
vertical source `x`, no flip. Raw arrays and affines are retained unchanged.
Checksums, source identity, section bounds and exact sampled centres are in
the metadata JSON.

## Stage 2 — external reference-space mapping

Status: **blocked before transformation; Stage 1 is preserved**.

The existing [EXTERNAL_MRI_EXECUTION_REPORT.md](EXTERNAL_MRI_EXECUTION_REPORT.md)
identifies the exact supported BigBrainWarp target as the ICBM2009c/ICBM2009
symmetric template named by upstream `scripts/init.sh`:

```text
spaces/tpl-icbm/tpl-icbm_desc-t1_tal_nlin_sym_09c_mask.mnc
```

The documented direction in upstream `icbm_to_bigbrain.sh` is an ICBM image
into BigBrain space using `BigBrainHist-to-ICBM2009sym-nonlin.xfm` with
`-invert_transformation`. Continuous T1w data requires the documented volume
interpolation; a binary ROI would require nearest-neighbour interpolation.
The upstream runtime requires MINC2 tooling and the exact nonlinear transform
plus every referenced displacement field.

The installed project environment does not contain the required runtime:

```text
command -v docker       -> /usr/bin/docker
command -v podman       -> unavailable
command -v mincinfo     -> unavailable
command -v mincresample -> unavailable
docker image inspect caseypaquola/bigbrainwarp:latest
  -> Error: No such image
```

The previous Docker recovery record shows the public image manifest was
accessible anonymously, but the pull stalled during final extraction and no
image was registered. Therefore the exact template, transform and referenced
field files were not available for a local execution. No template landmark,
ROI transform, transformed mask, section intersection or detailed patch was
attempted in Stage 2. No flips, inverse round-trip claims, registration or
anatomical labels were invented.

An expert must independently review any future Stage 2 mapped location. Even
if the documented runtime is installed, numerical transform success and
ROI/section overlap would remain separate from anatomical validation.

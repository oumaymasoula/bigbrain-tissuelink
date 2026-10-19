# Region navigation feasibility

## Result

Feasibility is demonstrated for one installed siibra parcellation and one
named region:

- Parcellation: **Cortical layer segmentation of the BigBrain model**
  (`juelich/iav/atlas/v1.0.0/3`).
- Region: **cortical layer 1 left**
  (`CORTICAL_LAYER_SEGMENTATION_OF_THE_BIGBRAIN_MODEL_CORTICAL_LAYER_1_LEFT`).
- Reference space: **BigBrain microscopic template (histology)**
  (`minds/core/referencespace/v1.0.0/a1655b99-82f1-420f-a3c2-fe80fd4c8588`).
- Installed client: `siibra==1.0.1-alpha.25`.
- Provider: [official configured cortical-layer Neuroglancer source](https://neuroglancer.humanbrainproject.eu/precomputed/BigBrainRelease.2015/2022_map_release/cortical_layers_left).
- API behavior: [siibra BigBrain high-resolution access example](https://siibra-python.readthedocs.io/en/latest/examples/02_maps_and_templates/004_access_bigbrain.html) and [parcellation API](https://siibra-python.readthedocs.io/en/latest/autoapi/siibra/core/parcellation/).
- Configuration source: [siibra-configurations](https://github.com/FZJ-INM1-BDA/siibra-configurations), loaded by the installed client at runtime.
- Region publication and attribution: [Wagstyl et al. 2020](https://doi.org/10.1371/journal.pbio.3000678).
- License reported by siibra: `CC BY-NC-SA 4.0`.
- Mask threshold: `0.0`; the mask is the labelled region mask, not a guessed probability cutoff.

The real mask provider was sampled in bounded Y slabs at the documented planes
of sections #3458 and #3500. Both fetched planes contained nonzero mask voxels:

| Section | Plane Y (mm) | Mask request | Actual mask grid (mm) | Nonzero voxels | Status |
|---|---:|---|---|---:|---|
| #3458 | -0.8595 | 0.2 mm requested | 0.169333 × 0.16 × 0.169333 | 12,638 | nonzero finite-Y slab; exact plane audited below |
| #3500 | -0.0195 | 0.2 mm requested | 0.169333 × 0.16 × 0.169333 | 18,872 | nonzero finite-Y slab; exact plane not audited |

These are bounded slab fetches. A nonzero slab is not, by itself, an exact
section-plane intersection: the slab has finite Y thickness and can contain
mask voxels on either side of the section plane.

## Bounded evidence

[evidence.json](outputs/region_feasibility/evidence.json) records the atlas,
region, threshold, space, mask affine, sampled plane, selected mask voxel,
section overview geometry, and bounded patch geometry.

[section_3458_region_overlay.png](outputs/region_feasibility/section_3458_region_overlay.png)
is preserved historical evidence from the original slab projection. It must
not be presented as a valid tissue-targeting overlay because it projected all
nonzero voxels in the finite Y slab.

[cortical_layer_1_left_mask_plane.nii.gz](outputs/region_feasibility/cortical_layer_1_left_mask_plane.nii.gz)
is the real bounded mask slab. Its former coordinate-wise-median point
`[-41.8173326, -0.8195, 9.0120007] mm` is retained only in the historical
evidence and is not used for targeting.

[region_intersecting_patch.nii.gz](outputs/region_feasibility/region_intersecting_patch.nii.gz)
is preserved earlier bounded evidence; its former coordinate-wise-median
selection is not used as the audited point.

## Exact-plane audit for #3458

[region_plane_audit.py](region_plane_audit.py) reproduces the bounded audit.
It samples the mask onto the exact section-plane display grid using both full
affines and nearest-neighbour categorical sampling. The display convention is
unchanged and explicit: the scientific array is `(x, y, z)`, while displayed
horizontal pixels are source `z` and displayed vertical pixels are source `x`;
there are no display flips. Slab overlap and exact-plane sampling are reported
separately.

The real audit produced:

- slab nonzero voxels: **12,638**;
- exact-plane nonzero display pixels: **11,137**;
- **6,998** of those pixels (62.84%) fall on overview pixels brighter than
  245 under the audit's background-like diagnostic threshold;
- actual nonzero display pixel selected (nearest the nonzero centroid):
  **UV `(611, 218)`**, not a coordinate-wise median;
- selected world point: **`(-38.56517694, -0.8595, 9.20420725)` mm**;
- bounded detailed patch: shape **`(251, 1, 251)`**, actual resolution
  **`(0.008, 0.02, 0.008) mm`**, and it contains the selected exact-plane
  mask voxel by bounds;
- provider region identity: **cortical layer 1 left**. Hemisphere is recorded
  from the provider identity; it is not inferred from the sign of X.

The clean diagnostic outputs are
[section_3458_region_exact_plane_diagnostic.png](outputs/region_feasibility/section_3458_region_exact_plane_diagnostic.png),
[section_3458_region_exact_plane_mask.png](outputs/region_feasibility/section_3458_region_exact_plane_mask.png),
and [region_exact_plane_audit.json](outputs/region_feasibility/region_exact_plane_audit.json).
The red diagnostic pixels are nearest-neighbour mask samples on the exact
plane, not validated tissue labels. The patch intersection is a numerical
reference-space check only; no anatomical review has been performed.
The background-like fraction demonstrates that a mismatch remains between the
mask and the displayed tissue image. It does not identify whether the cause is
provider semantics, sampling, section content, or anatomy, and no tissue
constraint, flip, registration, or correction was applied.

## Source-reconstruction comparison

[section_3458_source_reconstruction_vs_mask_same_world_grid.png](outputs/region_feasibility/section_3458_source_reconstruction_vs_mask_same_world_grid.png)
contains two separate panels sampled on the same world X/Z grid and requested
Y=`-0.8595 mm`: the local `full8_200um_optbal.nii.gz` reconstruction on the
left and the categorical cortical-layer mask on the right. The reconstruction
uses linear intensity sampling; the mask uses nearest-neighbour categorical
sampling. Each panel is independently display-normalized. The raw intensity
arrays and affines are not modified, and intensity differences are not treated
as alignment evidence.

The source reconstruction is NIfTI shape `(696, 770, 605)`, voxel size
`0.2 mm` in RAS/world units, with affine origin approximately
`(-70.6666, -72.9100, -58.7777) mm`. The mask is the configured
`cortical_layers_left` Neuroglancer segmentation dataset from the BigBrain
2022 map release, `uint32`, with 20–1280 µm scales; the audit used the
160 µm scale returned for the bounded 0.2 mm request. Its configured provider
is the left-hemisphere endpoint and its siibra space is the BigBrain
microscopic template. The exact provider metadata and both affines are stored
in [region_exact_plane_audit.json](outputs/region_feasibility/region_exact_plane_audit.json).

The world query Y is identical for both products, but native voxel centres are
not: the 200 µm reconstruction's nearest native Y centre is approximately
`-0.91 mm`, while the requested comparison grid is evaluated at `-0.8595 mm`.
This distinction is recorded rather than hidden. The source-reconstruction
comparison therefore confirms a consistent rendering/query convention, not
anatomical correspondence. The remaining displacement is unresolved.

## Integration scope and limitations

The optional region controls support this one atlas/region and show the two
sections with real mask-plane evidence. The rest of the 145 registered
sections remain untested for this region; the UI must call them “untested”,
not unavailable or intersecting. No anatomical region names are inferred
from intensity, section number, or visual similarity.

The first implementation was paused after the slab-overlay mismatch. The
corrected renderer supports an exact-plane diagnostic, but atlas navigation
remains **experimental and paused pending geometry review**. Do not expand to
additional regions or present the red mask as a tissue-targeting overlay until
an expert reviews the clean diagnostic. Scientific arrays and affines remain
unchanged. A mask intersection supports navigation and patch targeting only;
it is not a registration accuracy claim, MRI correspondence claim,
cellular-equivalence claim, or diagnosis. The current conclusion is:
**rendering consistency is supported; the cause of anatomical disagreement is
not established.**

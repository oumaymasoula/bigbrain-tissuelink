# Feasibility: section #3458 to the 200 µm BigBrain volume

Status: **documented reference-space mapping exists; exact anatomical
correspondence remains unvalidated**. This report does not change the app,
create a registration, or claim that equal world coordinates are identical
anatomical points.

## Scope

The tested high-resolution section is the existing downloader example:

- Section: `#3458`
- siibra identifier: `73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126`
- Dataset version: `73c1fa55-d099-4854-8cda-c9a403c6080a`
- siibra configuration: [section #3458 JSON](https://raw.githubusercontent.com/FZJ-INM1-BDA/siibra-configurations/v1/features/images/sections/cellbody/73c1fa55-d099-4854-8cda-c9a403c6080a_bigbrain_1um_3458.json)
- Provider: [`info`](https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed/info)
- Provider transform: [`transform.json`](https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed/transform.json)
- Provider URL recorded by the app: `https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed`
- Installed client tested: `siibra==1.0.1a25` / `1.0.1-alpha.25`

The 200 µm target is the local copy of the official
`3D_Volumes/Histological_Space/nii/full8_200um_optbal.nii.gz` release file:

- Local file: `outputs/spatial_feasibility/full8_200um_optbal.nii.gz`
- Shape: `(696, 770, 605)`
- Voxel size: `(0.2, 0.2, 0.2)` mm
- Affine: diagonal 0.2 mm with translation
  `(-70.6666031, -72.9100037, -58.7776985)` mm

## Evidence-backed mapping chain

The chain is:

```text
section pixel / provider voxel (B20_3458)
  -- provider transform.json + Neuroglancer voxel-centre convention -->
BigBrain microscopic reference-space world coordinates (mm)
  -- official BigBrain release's native histological-space volume affine -->
voxel coordinates in full8_200um_optbal.nii.gz
```

Each link is supported by a different source:

1. The official siibra configuration declares section #3458 in the
   BigBrain reference-space identifier
   `minds/core/referencespace/v1.0.0/a1655b99-82f1-420f-a3c2-fe80fd4c8588`
   and points to the registered-section provider. It does not merely use a
   matching filename.

2. The provider publishes an explicit transform, in nanometres:

   ```text
   [[0, 0, 1, -70677183.3333333],
    [0, 1, 0,   -869999.9999999994],
    [1, 0, 0, -58788283.3333333],
    [0, 0, 0,              1.0]]
   ```

   Its `info` declares `dataset_order=["z", "y", "x", "c"]`, 1 µm in-plane
   resolution, 20 µm thickness resolution, and one sample along thickness.

3. The installed siibra implementation contains the relevant upstream
   conversion in `siibra/volumes/providers/neuroglancer.py`:

   - `shift_ng_transfrom()` applies the provider transform and adds half a
     highest-resolution voxel to convert Neuroglancer coordinates to a
     standard NIfTI voxel-centre affine.
   - `NeuroglancerScale.fetch()` constructs the output image and applies
     `trans = identity[[2, 1, 0, 3], :]`, explicitly converting provider `zyx`
     storage to returned NIfTI `xyz` array order.

   For #3458 at the 1 µm scale, the resulting full-provider affine measured
   at runtime is:

   ```text
   [[0,     0,     0.001, -70.6766833333333],
    [0,     0.020, 0,     -0.8695000000000],
    [0.001, 0,     0,     -58.7877833333333],
    [0,     0,     0,       1.0]]
   ```

   The fetched crop affine is the same mapping translated to the requested
   crop origin. This is why the existing export can report physical section
   coordinates without inventing a transform.

4. The official BigBrain project states that the selected 1 µm scans are
   “aligned to the 20µm 3D-reconstructed BigBrain” in its [Maps & Models
   page](https://bigbrainproject.org/maps-and-models.html). The older raw-data
   README separately warns that the raw Huron rescans are not aligned to the
   previous acquisitions and describes them as candidates to be mapped to the
   20 µm aligned brain. The provider used by this app is the
   `registered_sections` product, not that raw-data directory.

5. The official release notes state that `3D_MRI` was added “in the final
   histological space” and should be compared with the histological-space
   volumes, while warning that the fit is imperfect. That MRI relationship is
   documented independently in [Updates.txt](https://ftp.bigbrainproject.org/bigbrain-ftp/BigBrainRelease.2015/Updates.txt#L100-L104).

## Runtime geometry check

The provider reports the #3458 bounding box as approximately:

```text
min = (-70.6766833, -0.8695, -58.7877833) mm
max = ( 68.4433167, -0.8495,  62.1122167) mm
```

The local 200 µm volume covers approximately:

```text
voxel-centre min = (-70.6666031, -72.9100037, -58.7776985) mm
voxel-centre max = ( 68.3333983,  80.8899994,  62.0223007) mm
```

The section is therefore inside the reconstructed volume's x/z coverage and
occupies the expected one-section-thickness y interval. For example, the
section y centre `-0.8595 mm` maps through the 200 µm affine to continuous
volume index `y≈360.25`; it is not treated as an array index copied from the
high-resolution provider.

This is a geometry/metadata consistency check, not an anatomical validation.
It does not compare tissue intensities, prove section identity against a
particular reconstructed slice, or estimate registration error.

## What is and is not established

### Established

- A supported high-resolution section has an explicit provider transform into
  the BigBrain microscopic reference space.
- The provider's source-axis order and the siibra conversion to returned NIfTI
  axes are explicit in metadata and upstream code.
- The official project describes the registered 1 µm product as aligned to the
  20 µm reconstructed BigBrain.
- The 200 µm volume is an official native histological-space volume with a
  usable NIfTI affine.
- A section pixel can therefore be transformed into reference-space millimetres
  and then located in the 200 µm volume by applying the inverse 200 µm affine,
  with explicit nearest-voxel or interpolation policy.

### Not established

- Exact intensity equivalence between a 1 µm registered section and the 200 µm
  volume. The 200 µm volume is reconstructed, optically balanced, and sampled
  at a different resolution.
- A guaranteed one-to-one correspondence between every high-resolution pixel
  and a 200 µm voxel, especially after downsampling and non-linear section
  processing.
- A validated anatomical error bound or uncertainty radius.
- A direct transform from the raw Huron scan files. The raw-data README
  explicitly says those rescans are not aligned to previous acquisitions; only
  the registered-section provider has the documented placement used here.
- Mapping of high-resolution annotations into MRI. That would additionally
  inherit the official imperfect MRI fit and requires a separate anatomical
  validation.

## Decision

The feasibility question is **positive for a documented reference-space
mapping** between the current registered high-resolution section #3458 and the
official 200 µm reconstructed volume. The mapping is provider-transform plus
two explicit NIfTI affines; it is not inferred from names, image appearance,
or coordinate-range coincidence.

This does **not** authorize a new linked viewer feature or automatic section
annotation placement. Any future implementation must keep raw pixels separate
from downsampled volume values, state the voxel-selection/interpolation rule,
retain the provider transform and both affines, and label the result as
reference-space placement rather than validated anatomical correspondence.

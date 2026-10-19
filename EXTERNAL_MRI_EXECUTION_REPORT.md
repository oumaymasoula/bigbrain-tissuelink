# External MRI execution milestone

Date: 2026-10-18

## Controlled retry on 2026-10-19

The local resource check before retry was:

```text
root filesystem: 937G total, 156G available, 83% used
inodes: 62,447,616 total, 57,810,953 free, 8% used
Docker client: 29.1.3
Docker server: 29.8.0
Docker driver: overlay2
Podman: command not found
mincinfo: command not found
mincresample: command not found
```

Docker was healthy and no pull was active. The public tag manifest was
inspected without downloading an image and pinned for the controlled retry:

```text
docker.io/caseypaquola/bigbrainwarp:latest
manifest digest: sha256:fdad755a90c865b72c65de827e144d715cdea35bc749351a0120cfd136080614
config digest: sha256:46b49a2e061660b69b1bebca46b952d430b952f17b0aeeeb4ee8db94d9ebe73e
```

The one bounded retry was:

```bash
timeout 120s docker pull docker.io/caseypaquola/bigbrainwarp@sha256:fdad755a90c865b72c65de827e144d715cdea35bc749351a0120cfd136080614
```

The initial observation window ended before registration, but the same
digest-pinned command was subsequently completed manually from the host. Its
reported exit status was `0`; every listed layer completed and Docker reported
the requested manifest digest. No prune, deletion or unrelated-image
operation was run.

The exact follow-up probe was logged separately:

```text
timeout 30s docker pull docker.io/caseypaquola/bigbrainwarp@sha256:fdad...
exit_code=124
elapsed_seconds=30
```

Exit code `124` was from the earlier bounded probe and is a timeout from the
`timeout` utility, not an image extraction error. Its log showed layers
waiting/downloading and checksum verification, with no error line. The later
manual completion confirmed that the image was publicly pullable and could be
registered successfully.

The verified local image is:

```text
RepoDigest: caseypaquola/bigbrainwarp@sha256:fdad755a90c865b72c65de827e144d715cdea35bc749351a0120cfd136080614
Image ID: sha256:46b49a2e061660b69b1bebca46b952d430b952f17b0aeeeb4ee8db94d9ebe73e
Size: 9,874,768,339 bytes
Created: 2023-07-28T09:24:48Z
```

The exact template and transform files are now available locally inside the
verified image. The earlier probe timeout was an observation-window limit,
not the final installation outcome.

Status: **container setup complete; full anatomical Stage 2 remains
incomplete**. The working application and its `.venv` were not modified.

## Docker recovery diagnostics

The configured runtime reports Podman, but Podman is not installed. Docker was
used only as the documented container fallback.

```text
Docker client: 29.1.3
Docker server: 29.8.0
Storage driver: overlay2
Docker root: /var/snap/docker/common/var-lib-docker
Free disk: 156 GB
Free inodes: 57,804,583 (92% free)
```

The exact requested image was:

```text
caseypaquola/bigbrainwarp:latest
```

The registry manifest was available. Its config digest was
`sha256:46b49a2e061660b69b1bebca46b952d430b952f17b0aeeeb4ee8db94d9ebe73e`.
The manifest contains a 2,192,807,829-byte layer. The completed image has
repository digest
`sha256:fdad755a90c865b72c65de827e144d715cdea35bc749351a0120cfd136080614`
and image ID
`sha256:46b49a2e061660b69b1bebca46b952d430b952f17b0aeeeb4ee8db94d9ebe73e`.

The first bounded probes timed out while layers were downloading. A later
manual retry completed all 19 layers with exit status `0`. Docker reported no
authentication, checksum, storage or daemon error. No Docker prune, image
deletion or unrelated process termination was performed.

## Authentication check

No credentials were requested and `docker login` was not run.

The raw registry endpoint returns the normal anonymous Bearer challenge:

```text
HTTP/2 401
www-authenticate: Bearer realm="https://auth.docker.io/token",
  service="registry.docker.io",
  scope="repository:caseypaquola/bigbrainwarp:pull"
```

This is a token challenge, not proof that the repository is private. Docker
obtained the public manifest anonymously:

```bash
docker manifest inspect caseypaquola/bigbrainwarp:latest
```

That command exited successfully and returned the manifest, config digest and
layer digests without a login. The image is publicly accessible anonymously at
the registry level.

The anonymous `docker pull` attempts did not report `unauthorized`,
`authentication required`, `denied`, or rate-limit errors. They downloaded and
verified layers, then stalled during final extraction/registration. The local
state afterward was:

```text
docker image ls caseypaquola/bigbrainwarp  -> digest-pinned image present
docker image inspect ...                  -> verified image ID above
```

Authentication was not the blocker. The initial observation was incomplete,
but the official Docker route is now available locally with MINC2 v2.

## Intended documented chain

```text
T1w/ROI already registered to the exact ICBM2009c symmetric template
  -> BigBrain native histological space
  -> registered detailed section #3458 reference coordinates
```

The exact BigBrainWarp template named by its upstream `scripts/init.sh` is:

```text
spaces/tpl-icbm/tpl-icbm_desc-t1_tal_nlin_sym_09c_mask.mnc
```

This is treated as ICBM2009c/ICBM2009sym, not as an unspecified “MNI” template.
BigBrainWarp's public `icbm_to_bigbrain.sh` uses
`BigBrainHist-to-ICBM2009sym-nonlin.xfm` with
`-invert_transformation` to resample an ICBM image into BigBrain space.
Volume interpolation is explicit; a label ROI would require
nearest-neighbour interpolation.

Sources:

- [BigBrainWarp installation](https://bigbrainwarp.readthedocs.io/en/latest/pages/installation.html)
- [BigBrainWarp transformation documentation](https://bigbrainwarp.readthedocs.io/en/latest/pages/scripts.html)
- [BigBrainWarp `init.sh`](https://raw.githubusercontent.com/caseypaquola/BigBrainWarp/master/scripts/init.sh)
- [BigBrainWarp `icbm_to_bigbrain.sh`](https://raw.githubusercontent.com/caseypaquola/BigBrainWarp/master/scripts/icbm_to_bigbrain.sh)
- [BigBrainWarp public data bundle](https://fz-juelich.sciebo.de/s/HoKucnh8zFpSbKF/download)

## Installation attempt

The configured container runtime was Podman, but Podman was unavailable. Docker
was available and its daemon responded. The official image was then requested:

```bash
docker pull caseypaquola/bigbrainwarp:latest
```

The initial bounded extraction did not complete within the execution window,
but the same digest-pinned pull was later completed manually with exit status
`0`. The image was registered at the digest above and a BigBrainWarp container
was run for the separate Stage 2 check.

The upstream repository head observed during this attempt was:

```text
68b068fbb93df49eb1339bf7a038876b4412577c
```

The upstream Dockerfile identifies the relevant runtime as MINC2 and Python
3.8. The official installation documentation specifies MINC2 v2 for volume
transforms and lists Workbench only for surface transforms.

The app environment was not changed. The app `.venv` still contains neither
BigBrainWarp nor MINC2 command-line tools.

The official setup was retried after the diagnostics:

```bash
docker pull caseypaquola/bigbrainwarp:latest
```

It again failed to reach a runnable registered image because extraction did not
complete; there was no reported checksum, storage, daemon or network error.

## Retrieved small public metadata

These files were retrieved successfully for the already validated detailed
section #3458:

| File | URL | SHA-256 |
|---|---|---|
| Provider info | `https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed/info` | `1bb62a6b7cb05d6dfb1b7d4af20cf8a2bc0abaeb007f18d7e392d29d59fc96e9` |
| Provider transform | `https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3458/precomputed/transform.json` | `b5be8972c4299067a4b05386625f958e90d7644e3a5fee2cedf1fc40c150b735` |
| siibra section configuration | `https://raw.githubusercontent.com/FZJ-INM1-BDA/siibra-configurations/v1/features/images/sections/cellbody/73c1fa55-d099-4854-8cda-c9a403c6080a_bigbrain_1um_3458.json` | `66907b9ff28813cfe353905290f50a1b95919f9c6e35d67cd422a65bd3dc19fc` |

The provider metadata reports `dataset_order=["z", "y", "x", "c"]`, 1 µm
in-plane resolution and 20 µm thickness resolution. The provider transform
is the published 4×4 nanometre transform used by the installed siibra
Neuroglancer reader.

The verified image contains the exact ICBM template and nonlinear fields. The
following SHA-256 values were computed inside the digest-pinned image:

| Asset | SHA-256 |
|---|---|
| `tpl-icbm_desc-t1_tal_nlin_sym_09c_mask.mnc` | `7febed81903d1330c369a3e47b4c603a07ddb6db984ac3165df9d0d0fe65e69c` |
| `BigBrainHist-to-ICBM2009sym-nonlin.xfm` | `154124103eba32e8c1dab21cb996d43d9046bd6c06d31dc2cefb19539b505104` |
| `..._grid_0.mnc` | `d8781a6dd3cde6669f6fa0fdf8b13089935a8e86b816b54acfc3164177e6378e` |
| `..._grid_1.mnc` | `b35001aebad81b0a0715c3b2e4aecfd760e7436ad2986c1496f1363684dc48a0` |
| `..._grid_2.mnc` | `60823988f6e1abe1080f8007f6dce9f731727622d947524aa8541b904c477492` |
| `..._grid_3.mnc` | `fa97075c8cb0782706c9927297b003b0aa3fb3e504560a98e74bb8d678537948` |

The XFM explicitly references all four grid files by basename. Their headers
were readable and all have vector dimension 3; grid 0 is 332×380×288 and
grids 1–3 are 197×233×189 in x/y/z physical dimensions (reported by MINC in
z/y/x dimension order).

## Public section execution check

The existing bounded public example was rerun independently:

```bash
./.venv/bin/python validate_real_data.py
```

Result: successful provider retrieval for section #3458. The existing export
and direct siibra fetch matched exactly (`raw_array_equal=true`,
`max_abs_raw_difference=0`), with shape `(251, 2, 251)` and returned voxel
size approximately `(0.008, 0.020, 0.008)` mm. This validates the provider
segment only; it is not an external-MRI transformation test.

## Separate Stage 2 execution status

The verified image was used for a bounded technical execution. The exact
bundled ICBM2009c symmetric mask was passed through the official
`icbm_to_bigbrain.sh` route as a nearest-neighbour input, with output
resolution 2 mm and `histological` target space:

```bash
source /BigBrainWarp/scripts/init.sh
/BigBrainWarp/scripts/icbm_to_bigbrain.sh \
  "$icbmTemplate" histological nearest 2 stage2_template_mask /work/out
```

Observed result:

```text
output: tpl-bigbrain_desc-stage2_template_mask_histological.mnc
shape: 70 × 70 × 70 (MINC z/y/x order)
spacing: 2 mm on all axes
start: z=-58.7777, y=-72.51, x=-70.6666 mm
values: unsigned byte; min=0; max=1
```

The output was finite and binary, and the transform direction and
nearest-neighbour mode were confirmed from the executed command and the
script's `-invert_transformation` call. The script emitted two
`command not found` warnings caused by invisible characters on lines 60 and
64 of the upstream shell script, but continued successfully and completed
both resampling stages. This is a technical transformation check, not
anatomical validation.

Still unperformed:

- transform a public ICBM2009c-registered T1w image (none was supplied or
  independently identified in this run);
- define an independently identifiable template landmark ROI;
- inspect the transformed mask anatomically against a source reconstruction;
- establish exact-plane intersection with section #3458 (the 2 mm output grid
  does not sample its documented Y plane exactly);
- fetch a detailed patch conditionally on a verified transformed-ROI
  intersection.

Therefore the container and transform feasibility milestone succeeded, but
the external-MRI anatomical Stage 2 milestone did **not** pass. No MRI upload
controls or automatic registration were added.

## External ROI-to-section feasibility audit

The separate audit was executed with the verified `.venv` and official
siibra configuration:

```bash
./.venv/bin/python external_roi_feasibility.py
```

The input was the exact distributed binary template mask
`tpl-icbm_desc-t1_tal_nlin_sym_09c_mask.mnc`, converted without changing its
values or affine. It is recorded as a template validity mask, not as an
anatomical ROI. The input NIfTI geometry was 193×229×193 at 1 mm with affine
origin `[-96, -132, -78]` mm and nonzero world bounds
`[-72,-107,-72]` to `[72,73,82]` mm.

The transformed output was sampled on the official BigBrain classified-volume
reference grid at 2 mm using nearest-neighbour interpolation. It was 70³ with
affine origin `[-70.666603, -72.510002, -58.777699]` mm, nonzero world bounds
`[-66.666603,-70.510002,-50.777699]` to `[65.333397,65.489998,53.222302]`
mm, and binary values 0–1. The full affine was used for all world-to-voxel
samples.

All 145 discovered registered-section planes were tested at their documented
world Y. Exact-plane nearest-neighbour sampling on the section X/Z extent
found 133 sections with nonzero mask samples; 12 sections (#6853, #6899,
#6951, #7001, #7050, #7103, #7150, #7200, #7250, #7300, #7350 and #7400)
were zero at the tested plane. These are technical mask results, not
anatomical matches.

One bounded real provider fetch was performed at the first candidate, section
#47, only after exact-plane membership was found. The selected point was
`[-18.666603, -69.0795, 3.222301]` mm. The returned patch was 251×5×251 with
voxel size approximately `(0.008, 0.020, 0.008)` mm. The centre returned
non-padding values on patch Y index 2; 5,422 voxels overlapped the sampled
mask after excluding observed padding values 0 and 255. This is extraction
evidence only. Section #47 is not treated as anatomically validated, and the
image is not used as proof that the whole section is usable.

Evidence files are kept under the ignored
`outputs/external_roi_feasibility/` directory, including the input and
transformed views, section overlay, raw patch, NIfTI/MINC products and
`external_roi_stage2_metadata.json`. The exact commands, section IDs,
affines, bounds, checksums and warnings are recorded in that JSON.

An independent anatomical landmark was not prepared: the bundled
`CREATORS_mni_icbm152.txt` contains provenance/licensing text but no documented
landmark. No coordinate was invented or labelled anatomically; an expert must
provide a documented template landmark before a candidate BigBrain point can
be reviewed.

Licensing to retain in a future implementation: BigBrain dataset terms from
the [official BigBrain license/source page](https://bigbrainproject.org/maps-and-models.html),
and BigBrainWarp's [GPL-3.0 license](https://github.com/caseypaquola/BigBrainWarp/blob/master/LICENSE).

## CerebrA left-precentral ROI experiment

The preserved CerebrA experiment under
`outputs/external_roi_feasibility/cerebra/` was resumed without rerunning or
overwriting its completed BigBrainWarp transform. The release archive contains
exactly `mni_icbm152_CerebrA_tal_nlin_sym_09c.nii` and
`CerebrA_LabelDetails.csv`; its SHA-256 is
`51ae4a9a2d004c3c0edea2e3ab0c15f71a2c88f04960aa2e599a3633816f445d`.
The original download URL was not retained, so the archive checksum and its
contents are the available local provenance record; a source URL is not
reconstructed from memory.

### Exact identity and compatibility

The source filename and NIfTI header identify the atlas grid as
`mni_icbm152 ... tal_nlin_sym_09c`, rather than an unspecified MNI space. The
atlas and the exact ICBM input prepared for BigBrainWarp are both
193×229×193, 1 mm, RAS, with identical affines (array equality; maximum
absolute difference 0):

```text
[[   1,    0,    0,  -96],
 [   0,    1,    0, -132],
 [   0,    0,    1,  -78],
 [   0,    0,    0,    1]]
```

This is an exact grid/affine compatibility result with the distributed
BigBrainWarp ICBM2009c symmetric template mask, not a name-only match. The
CerebrA label table records Precentral as RH label 35 and LH label 86. The
saved ROI is exactly `(atlas == 86)`, contains 21,393 voxels, has world bounds
`[-66,-36,-1]` to `[-5,14,81]` mm and centroid X `-42.757 mm`; these facts
independently support the recorded left-hemisphere identity.

Input checksums are:

| Asset | SHA-256 |
|---|---|
| CerebrA atlas | `8cbb7a90a8ae6f34001a1d659d99c9480dd79121184c2e2f01b160ad32d7800c` |
| CerebrA label table | `16ba5fec63159b69699d17d79274d34ec68d14099c3c989dadbbed83e2da9999` |
| Binary left-precentral ROI | `99b5ee39c809c4f187dfc193a6dc61ca862956bf4b86f6810933f4815885a098` |
| BigBrainWarp ICBM input | `9f4a433a64fb3f6470b6f6fa5d6194fcc3b827ce0e2e882d6d5fa0f17626f32d` |

### Transform and technical result

The preserved transformed output is 70³ at 2 mm on the BigBrain classified
reference grid, is binary 0–1, contains 1,116 nonzero voxels, and has world
bounds `[-62.666603,-6.510002,-4.777699]` to
`[-18.666603,31.489998,53.222301]` mm. Its SHA-256 is
`166c2ab681c7653d269695c7542d5a91283a6e02a5c87b087d624780d5d9fada`.

Direction is ICBM2009c symmetric input to BigBrain histological output: the
fixed upstream `icbm_to_bigbrain.sh` route applies
`BigBrainHist-to-ICBM2009sym-nonlin.xfm` with
`-invert_transformation`. Nearest-neighbour interpolation is consistent with
the preserved binary output. The saved reference MINC history independently
records `mincresample -nearest_neighbour` for the 2 mm reference grid. No
CerebrA-specific transform shell log was saved, so the exact invocation cannot
be quoted verbatim; direction and interpolation are reported as file/script
evidence, not as a recovered command transcript.

Exact-plane nearest-neighbour sampling of all 145 registered sections found
39 intersecting planes, from #3146 at Y=-7.0995 mm through #5102 at
Y=32.0205 mm. This set includes #3458 and #3500. The complete per-section
record is in `cerebra_left_precentral_feasibility.json`.

One bounded provider patch was fetched only after mask membership was found:

```text
section: #3146
selected world point: [-22.666603, -7.0995, 47.222301] mm
requested bounds: [-23.666603,-7.1395,46.222301] to
                  [-21.666603,-7.0595,48.222301] mm
returned shape: 251×5×251
returned spacing: approximately [0.008,0.020,0.008] mm
mask/non-padding overlap by Y: [0,0,62268,0,0]
patch SHA-256: 8f825fd07e75afcf5ec188bea00ee53d5f6d68ca0db0493602a369f59b491393
```

The overlap is confined to the returned source plane; the four other provider
planes do not contribute overlap. This is a technical spatial-overlap result,
not evidence that the transformed parcel is anatomically correct.

### Review artifacts and anatomical status

New, non-overwriting review artifacts are:

- `cerebra_left_precentral_source_template_review.png`: CerebrA source labels
  with label 86 highlighted at source Y=0 mm;
- `cerebra_left_precentral_bigbrain_review.png`: transformed mask over the
  local 200 µm BigBrain reconstruction at Y=13.49 mm;
- `cerebra_left_precentral_section_patch_review.png`: bounded #3146 patch and
  sampled-mask overlay;
- `cerebra_left_precentral_section_patch.nii.gz`: raw provider patch;
- `cerebra_left_precentral_feasibility.json`: complete geometry, checksums,
  all section tests and fetch evidence.

Technical status: **passed for exact source-grid compatibility, label
extraction, transform-output integrity, section intersection and bounded patch
overlap**.

Anatomical status: **not independently reviewed**. An expert still needs to
judge the source and BigBrain paired views and confirm that the transformed
left-precentral location is anatomically plausible. No app upload or automatic
registration feature is enabled by this experiment.

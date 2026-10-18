# External MRI execution milestone

Date: 2026-10-18

Status: **blocked before image transformation**. The working application and
its `.venv` were not modified.

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
The manifest contains a 2,192,807,829-byte layer. No local repository digest
or image ID became available because the image never completed registration.

Two pull attempts downloaded and verified many layers, then remained idle
during final extraction/registration. Docker reported no error, the daemon
returned normally to `docker info`, and the daemon journal contained no
entries for the pull interval. The two exact stalled pull processes were
stopped after inspection. No Docker prune, image deletion or unrelated process
termination was performed.

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
docker image ls caseypaquola/bigbrainwarp  -> no image
docker image inspect ...                  -> No such image
```

Authentication is therefore not the blocker. The blocker is incomplete local
image download/extraction. Official alternatives remain the documented
BigBrainWarp local installation using MINC2 v2, or the same official Docker
image after the local Docker extraction issue is resolved; neither was started
automatically.

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

Layers downloaded, but the final extraction did not complete within the
execution window and the image was not registered. The pull was stopped. No
BigBrainWarp container was run.

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

The BigBrainWarp cloud bundle containing the exact ICBM template and nonlinear
fields was not extracted, so its archive checksum and the checksums of
`BigBrainHist-to-ICBM2009sym-nonlin.xfm` and its referenced displacement field
are not claimed here.

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

## Required execution still outstanding

The following checks could not be performed because the isolated BigBrainWarp
runtime and exact data bundle were not available:

- verify every displacement field referenced by the nonlinear `.xfm` exists;
- checksum the exact ICBM template, `.xfm`, and displacement grid;
- transform a public ICBM2009c-registered T1w image;
- transform a matching ROI with nearest-neighbour interpolation;
- verify transformed geometry and ROI labels;
- determine whether the transformed ROI intersects section #3458;
- fetch a detailed patch conditionally on that intersection.

Therefore the required milestone did **not** pass, and no MRI upload controls
or automatic registration were added.

Licensing to retain in a future implementation: BigBrain dataset terms from
the [official BigBrain license/source page](https://bigbrainproject.org/maps-and-models.html),
and BigBrainWarp's [GPL-3.0 license](https://github.com/caseypaquola/BigBrainWarp/blob/master/LICENSE).

# Labelme → COCO adapter

The only downstream format currently supported is COCO instance-segmentation
JSON, chosen because the preserved user-created annotation is native Labelme
JSON and the official Labelme repository documents `labelme2coco.py` as its
COCO conversion path:

- [Labelme README](https://github.com/wkentaro/labelme) documents COCO export
  for instance segmentation and the stable on-disk JSON format.
- [Official Labelme instance-segmentation example](https://github.com/wkentaro/labelme/tree/main/examples/instance_segmentation)
  documents `labelme2coco.py`, `images/` and `annotations.json` output.
- [Official converter source](https://github.com/wkentaro/labelme/blob/main/examples/instance_segmentation/labelme2coco.py)
  is the reference for polygon segmentation, category, bounding-box, area and
  `iscrowd` fields. The adapter uses only polygon shapes, matching TissueLink's
  validated input.

## Export contract

The Advanced Labelme import panel offers **Export COCO instance-segmentation
package** after a polygon has been accepted. The ZIP contains:

```text
images/<exact-unmarked-png>
annotations/instances_<patch-id>.json
canonical/<patch-id>.nii.gz
canonical/<patch-id>_metadata.json
README.txt
```

The COCO JSON contains PNG pixel coordinates, image dimensions, user-label
categories, polygon segmentation, pixel area, pixel bounding boxes and
`iscrowd=0`. It does not contain or imply NIfTI voxel coordinates, affines,
world millimetres, slice identity or anatomical correspondence. Those remain
in the canonical NIfTI and TissueLink metadata in the same package.

Labels are user annotations, not verified anatomical labels. The adapter does
not resample, resize, flip, register or infer anatomy. It uses the original
unmarked PNG, not a marked or enlarged preview.

## Compatibility status

The adapter is schema-tested against the official field contract and preserves
the canonical spatial files. The current environment does not have a COCO
viewer/consumer installed, and the official Labelme GUI was not operated by
this agent, so opening the generated artifact in a target application remains
**compatibility unverified**. Do not treat JSON-schema and ZIP checks as an
application-level visual validation.

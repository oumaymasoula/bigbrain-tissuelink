# Native Labelme polygon import

This is one optional Advanced workflow for annotating a collection patch. It
accepts native Labelme polygon JSON, the exact collection `metadata.json`, and
the exact unmarked PNG exported for the selected patch. Labelme is not required
for the main TissueLink workflow.

## Identity checks

The importer requires the collection patch ID, section ID, provider identity,
coordinate space, source-array checksum, PNG filename, PNG SHA-256 checksum,
PNG dimensions, selected Y index, NIfTI shape and full affine to agree. A
dimensions-only match is rejected. Unsupported Labelme shapes, embedded image
data, non-PNG/non-grayscale images, non-finite vertices and out-of-bounds
vertices are rejected with explicit errors. Imported labels remain user labels;
they are not anatomical labels.

## Coordinate convention

The unmarked PNG is the contrast-adjusted visualization of
`data[:, selected_y, :].T`. Labelme coordinates are `(u, v) = (x, y)` with
origin at the top-left. Integer coordinates identify pixel centres. The exact
mapping is:

```text
PNG pixel (u, v) -> NIfTI voxel (i_x=u, i_y=selected_y, i_z=v)
world_mm = full_source_affine @ [i_x, i_y, i_z, 1]
```

No flip, resize, rotation, registration or silent axis swap is applied. The
original polygon vertices are preserved in `polygon_annotations.json` in PNG
pixels, NIfTI voxel coordinates and world millimetres.

## Labelled mask

The exported `label_mask.nii.gz` has shape `(width, 1, height)`, uses the
selected Y plane only, and carries a crop-adjusted affine whose translation is
the source affine evaluated at `(0, selected_y, 0)`. It is not extruded across
other slices. Label IDs are `0=background` and `1..N` in Labelme shape order;
the explicit table is in `label_table.json`. Vertices are rounded to the
nearest pixel before PIL polygon fill. When polygons overlap, later shapes in
JSON order overwrite earlier shapes. Out-of-bounds vertices are rejected before
rasterization.

The source PNG is included unchanged for audit. It is distinct from marked
preview images and from raw scientific NIfTI values.

## Verification status

Automated tests cover a non-square patch, nonzero Y slice, asymmetric polygon,
nontrivial affine, exact PNG checksum and dimensions, mismatch rejection,
world-coordinate conversion, mask placement and single-plane export. A native
Labelme JSON schema path is implemented, but an actual external Labelme GUI
round trip has **not** been completed; the project does not claim that result
until a user-created Labelme file is imported and inspected.

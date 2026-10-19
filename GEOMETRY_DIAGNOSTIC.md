# World-grid geometry diagnostic

This diagnostic is separate from the TissueLink interface and does not alter
scientific arrays, affines, collections or exports. It compares the registered
section overview for #3458 with the reconstructed 200 µm volume using the
selected point:

```text
XYZ = [-24.40545688637588, -0.8595, 28.791557760299625] mm
```

## Method

`geometry_diagnostic.py` applies the full inverse affine independently to
every point on one shared world X/Z grid. It uses nearest source voxel centres,
no interpolation, no display flip and no registration. Both images use:

- bounds X = `-70.6666030883789 … 68.33339691162308 mm`;
- bounds Z = `-58.7776985168457 … 62.02230148315601 mm`;
- spacing = `0.2 × 0.2 mm`;
- shape = `605 rows × 696 columns`;
- horizontal axis = world X; vertical axis = world Z;
- selected point = shared-grid pixel `(u=231, v=438)` in both panels.

The registered overview affine and reconstructed-volume affine are retained in
`outputs/geometry_diagnostic/metadata.json`. The selected point is marked on
both independently rendered panels and on the paired image.

## Synthetic rendering validation

The test fixture uses a non-square `(4, 2, 5)` source with an axis-permuting
affine and an off-diagonal X/Z term. Its pixel values encode source indices,
and two asymmetric landmarks were recovered through the actual grid sampler.
The renderer test confirms the same off-centre `(u, v)` marker appears in both
panels. This is not only a helper-to-helper inverse round trip.

## Real result

The bounded real diagnostic completed successfully. All `421080` shared-grid
samples were valid for both images. The paired image shows the selected marker
at the same grid position in both panels.

Each image is normalized independently for display. The checkerboard and
opacity images blend those separately normalized displays; they do not blend
raw intensities. Raw cross-product intensity differences are deliberately not
used as alignment evidence.

This diagnostic supports rendering consistency: the two products use the same
world-grid extent, orientation, scale, marker position and full-affine
sampling policy. The cause of any anatomical disagreement is not established.
It may reflect the distinct source products, sampling and imperfect fit, but
this diagnostic does not distinguish those possibilities.

The exact source-space metadata is recorded in
`outputs/geometry_diagnostic/metadata.json`, including section #3458's
provider transform and dataset order, both volume sources and affines, and the
requested versus nearest sampled Y centres (`-0.8695 mm` for the registered
overview and `-0.910002589225769 mm` for the 200 µm volume).

## Independent landmark review

The reviewer should choose three recognizable features separately in each
clean image. Do not copy coordinates from one panel to the other and do not
assign anatomical names unless independently established. Record the image
pixel and world XYZ coordinate for each observation in
`LANDMARK_REVIEW_TEMPLATE.json`, then calculate each pairwise Euclidean
separation in millimetres. These are landmark discrepancies, not an accuracy
score or proof of correspondence. The template intentionally contains no
pre-filled landmarks.

The clean images are independently normalized and unmarked for anatomical
review. The marked images and overlays are for locating the selected point and
checking the shared-grid geometry.

## Reproduce

```bash
.venv/bin/pytest -q
.venv/bin/python geometry_diagnostic.py \
  --output-dir outputs/geometry_diagnostic
```

Local outputs:

- `outputs/geometry_diagnostic/registered_world_grid_selected.png`
- `outputs/geometry_diagnostic/histology_world_grid_selected.png`
- `outputs/geometry_diagnostic/paired_world_grid_selected.png`
- `outputs/geometry_diagnostic/metadata.json`

The output directory is ignored as generated data and remains local.

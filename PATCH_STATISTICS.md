# Descriptive patch statistics

TissueLink reports optional intensity descriptions for the raw scientific
NIfTI plane used for the detailed preview. These values are descriptive only;
they are not tissue-quality, cell-density, tissue-fraction, tear, fold or
anatomical-validity measurements, and they never discard a patch.

The display plane is the renderer-selected `data[:, y, :]` plane. If that
plane contains only declared provider padding, the implementation selects the
plane with the most finite non-padding pixels, then the greatest intensity
range. The raw array and affine are never modified. Current provider padding
is declared as value `255`; this is a source/padding convention, not a claim
that intensity 255 is biologically background in every dataset.

Definitions:

- `status=empty_or_padding` means no finite pixel remains after excluding the
  declared values; `constant` means all remaining finite values are equal;
  `variable` means their range is nonzero.
- `declared_background_fraction_of_finite` is the count of finite pixels equal
  to a declared value divided by all finite plane pixels.
- Percentiles are the 1st, 5th, 50th, 95th and 99th percentiles of finite,
  non-declared values. No contrast-adjusted preview pixels are used.
- Saturation is the fraction of usable integer pixels exactly equal to the
  storage dtype minimum or maximum. It is not reported for floating-point
  arrays because no storage endpoints are assumed.
- Sharpness is the mean squared four-neighbour Laplacian over valid interior
  pixels: `mean((4*c - up - down - left - right)^2)`. Pixels that are
  nonfinite, declared padding, or adjacent to either are excluded.

Users may record a keep/exclude decision and free-text reason in the app.
Those are user annotations, not automatic quality judgments.

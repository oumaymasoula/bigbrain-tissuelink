# Bounded patch sampling

TissueLink can generate a bounded sampling plan on the currently selected
registered section. This is a geometric rectangle sampler, not anatomical
region sampling and not automatic segmentation.

## Workflow

1. Select one registered section and click the detailed-section overview.
2. Open **Experimental · sample patches within this rectangle**.
3. Edit the physical X/Z rectangle and patch dimensions.
4. Choose **Regular grid** or **Seeded random**.
5. Click **Generate sampling plan** and inspect every cyan footprint.
6. Click **Fetch sampling plan** only after reviewing the plan.

The plan stores the exact section ID, Y bounds, rectangle, patch dimensions,
spacing or count, seed, generated centres and request resolution. Random plans
record `numpy.random.Generator(PCG64)`, the sampler version and NumPy version;
replay uses the stored centres and does not redraw them.

## Sampling rules and limits

- A complete patch footprint must remain inside the selected rectangle.
- Overlap is allowed and recorded; duplicate centres are rejected.
- No background filtering is applied. A returned background-only patch is
  reported separately and is not substituted or silently removed from the
  requested plan.
- At most 8 patches and 8 provider requests are allowed per plan.
- Estimated raw request data are capped at 10 MiB, in addition to the
  existing provider request budget.
- Requested centres and retrieval results are separate records. Results are
  `retrieved`, `background_only`, or `failed` and include the error when one
  occurs.
- Successful sampled patches are added to the existing session collection;
  changing sections does not delete them. Streamlit session state is not
  persistent across refreshes, so download the collection ZIP.

The existing scientific arrays and affines are not modified. Exported sampled
patches retain native provider values and include the sampling plan in their
metadata. User notes are not interpreted as anatomical labels.

## Verification status

The deterministic sampler, bounds, duplicate rejection, metadata recording
and limit checks are covered by automated tests. The live Explorer displayed
the controls and preview-before-fetch workflow on port 8504. A fresh bounded
real-provider sampling smoke check for #3458 was attempted but could not run in
that session because the installed siibra configuration mirrors were
unavailable through DNS (`NoSiibraConfigMirrorsAvailableException`). Existing
historical #3458 provider/export evidence is not counted as a fresh sampling
run. A real sampling retrieval remains outstanding.

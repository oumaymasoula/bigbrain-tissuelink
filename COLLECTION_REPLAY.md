# Collection reopening and replay

TissueLink collection exports now include a versioned `manifest.json`. It is
a data record for bounded replay, not an executable recipe. A collection can
be reopened locally without contacting the provider, or explicitly re-fetched
from the recorded parameters.

## Actions

In the Explorer, open **Patch collection → Reopen or re-fetch a collection**
and upload a ZIP.

- **Reopen collection (inspect only)** validates the archive, path safety,
  patch count, decompressed-size limits, manifest/metadata, raw-array
  checksum, expected shape and affine. It does not fetch data.
- **Re-fetch collection** first displays the number of bounded requests and
  the maximum recorded request budget. It does nothing until the button is
  explicitly pressed. Each result is `reproduced`, `changed`, `failed`, or
  `unsupported`.

The collection remains session-scoped. Download the resulting ZIP if it must
be retained across a browser refresh.

## Manifest contract

Manifest schema `bigbrain-tissuelink.collection-replay` version `1.0` records
for every patch:

- registered section ID and provider provenance;
- coordinate space, requested bounds, requested resolution and request budget;
- expected shape and affine;
- actual voxel size, raw-array SHA-256 and serialized-NIfTI SHA-256;
- annotation-PNG normalization and pixel mapping when present; and
- software versions.

The raw-array checksum is compared independently from the serialized-file
checksum. Scientific replay compares raw array values, shape and affine using
an affine absolute tolerance of `1e-5 mm`; actual returned resolution is also
reported. A serialized checksum can change because of file-header or
compression details without changing the scientific array.

## Compatibility and safety

Pre-manifest TissueLink ZIPs are accepted through a read-only compatibility
adapter that derives a replay view from each `metadata.json`. Missing replay
parameters are reported as `unsupported`; they are never guessed. Imported
labels, notes, paths and URLs are treated as untrusted metadata. The adapter
rejects malformed ZIPs, unsafe paths, duplicate members, oversized archives,
oversized decompressed content, excessive patch counts and unsupported
providers. Only the configured HTTPS registered-section provider is accepted,
and re-fetch uses the recorded section ID through the app's existing bounded
`fetch_crop` function. Manifest URLs are never opened or executed.

## Validation record

Automated replay tests cover successful replay, legacy adaptation, corrupted
and unsafe archives, missing parameters, changed provider output and partial
failure. A real bounded #3458 replay was run locally using the preserved
legacy export's section/provider/bounds and its documented original
`0.01 mm` request resolution. It returned `reproduced`: raw-array checksum,
shape, affine, actual voxel size and serialized-NIfTI checksum all matched.
Because the old ZIP did not record requested resolution, this was an explicit
legacy-parameter reconstruction, not evidence that the old manifest contained
that field.

Browser verification was also performed with a temporary manifest-bearing ZIP
derived from the preserved real #3458 export: upload, **Reopen collection
(inspect only)**, manifest/patch-count inspection, bounded-work estimate, and
the explicit **Re-fetch collection** action all completed. The replay-results
table appeared in the app. The exact scientific row values were independently
checked through the Python provider replay above; this browser check did not
constitute anatomical validation.

# Registered section catalogue validation

This report covers the section selector added to the main MRI–histology
explorer. Discovery uses the installed `siibra==1.0.1-alpha.25` public
configuration and the `CellbodyStainedSection` feature query. Records are kept
only when the configured provider metadata identifies the
`/registered_sections/` endpoint. No provider URL or coordinate was inferred
from a section number, and no raw or unaligned provider was included.

## Catalogue

The runtime discovered **145 registered sections**. Each catalogue record
contains:

- the siibra section identifier and provider source URL;
- the official coordinate-space name, physical x/y/z bounds, and the section
  plane centre (`(min_y + max_y) / 2`);
- all provider scales and voxel sizes;
- the provider dataset order and full provider transform in nanometres;
- separate metadata-retrieval and real-fetch-verification statuses.

The section selector is metadata-first. It does not fetch every image. A
selected section's overview and detailed crop are fetched only after the user
selects it and requests the bounded image.

Plane coverage is Y=`-69.0795` to `+77.9805` mm. Adjacent-plane spacing has
median `1.0000` mm, minimum `0.6200` mm, and maximum `2.0800` mm. The largest
gap is `2.0800` mm, between planes `-16.9595` and `-14.8795` mm. These are
provider section-plane centres; they are not a claim of continuous tissue
coverage between planes.

## Real-fetch verification

All requests used the existing 10 MiB cap, a 2 mm × section-thickness × 2 mm
bounded request, and requested resolution `0.01 mm`. The provider selected
`[0.008, 0.020, 0.008] mm` in every verified case. The existing #3458 result
remains the reference example.

| Section | siibra identifier | Plane centre Y (mm) | Returned shape | Non-background samples (`<250`) | Export round-trip |
| --- | --- | ---: | ---: | ---: | --- |
| #3407 | `73c1fa55-d099-4854-8cda-c9a403c6080a--612c5d516253fb09e1b247ea6da33347` | -1.8795 | `(251, 1, 251)` | 62,977 | raw values, shape and affine passed |
| #3500 | `73c1fa55-d099-4854-8cda-c9a403c6080a--b0738367ed7b5255928960dd9b97f16f` | -0.0195 | `(251, 1, 251)` | 45,620 | raw values, shape and affine passed |
| #3556 | `73c1fa55-d099-4854-8cda-c9a403c6080a--058be27aabda4ed18034c27271540393` | 1.1005 | `(251, 1, 251)` | 48,153 | raw values, shape and affine passed |

The three sources are:

- #3407: `https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3407/precomputed`
- #3500: `https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3500/precomputed`
- #3556: `https://1um.brainatlas.eu/registered_sections/bigbrain/B20_3556/precomputed`

For each section, the fetched NIfTI was written to a temporary export with
the existing `export_crop` helper and read back with nibabel. The raw array
was exactly equal, the shape matched, the affine was equal within `1e-6`, and
metadata was present. The provider metadata reported dataset order
`["z", "y", "x", "c"]`; the transform maps provider nanometres to the
documented BigBrain microscopic-template reference space. The returned NIfTI
affine has x/y/z axes and preserves the section's y-thickness representation.

## Failed or not-counted checks

Section #47 was discovered correctly. Its first bounded tile returned
constant 255 values, but a later overview-guided high-resolution tile
returned tissue-containing values. The initial all-background result is
therefore inconclusive; it is not evidence that the whole section is
unusable. Section #47 is included in the fetch-verified set below, and was
not substituted with another section. Section #500 also returned
non-background values in a bounded high-resolution request, but it is not
part of the three-section export round-trip table above.

These are software/data-availability checks, not anatomical validation. A
non-background value does not identify a neuroanatomical region or prove
MRI-to-histology correspondence.

## Catalogue-spread overview checks

To avoid testing only near #3458, full bounded overviews at requested
`0.128 mm` were inspected at three widely separated planes:

| Section | Plane centre Y | Overview result | Detailed follow-up |
| --- | ---: | --- | --- |
| #47 | -69.0795 mm | Small visible tissue island in the overview | 2 mm bounded patch passed: `(251, 1, 251)`, range `0..255`, 62,942 values `<250` |
| #3500 | -0.0195 mm | Broad tissue-containing overview | 2 mm bounded patch passed: `(251, 1, 251)`, range `20..255`, 333 values `<250` |
| #7400 | 77.9805 mm | Small visible tissue island in the overview | Overview-derived high-resolution tile returned constant `255`; inconclusive, not counted as a failed whole section |

The #47 and #3500 detailed requests selected `[0.008, 0.020, 0.008]`
mm actual voxel sizes. #7400 remains metadata-discovered and overview-
retrieved, but its detailed tissue location requires further investigation;
the application does not substitute another plane or claim that #7400 is
unusable.

Across the current checks, the fetch-verified set is #47, #500, #1001,
#3407, #3458, #3500 and #3556. The three-section table above records the
earlier round-trip set; the separate two-section export check below records
#47 and #3500.

## Automated two-section export check

An automated equivalent of the requested two-section export sequence was
run for the widely separated sections #47 and #3500 using the existing
`export_crop` helper and identical bounded request geometry. Both exports
contained `bigbrain_crop.nii.gz`, `bigbrain_crop_preview.png` and
`metadata.json`; both NIfTI files opened successfully with shape
`(251, 1, 251)`, actual voxel sizes
`[0.00800000038, 0.01999999955, 0.00800000038]` mm, and matching affines.
The raw arrays were exactly equal to fresh provider fetches. The NIfTI
checksums were respectively
`7db440d21459591f48b16b256eb32110152593fa5413aba11258760258c782f3`
and
`b7b119a0abaa4fde90ce694f036ddd3e154b3c554a042caa235839b06c1e33fb`;
each matched its metadata checksum. The second metadata contained #3500’s
identifier, source URL, plane and bounds, with no stale #47 identity.

## Manual browser check

The manual check was not completed. The application server rendered on port
8513, but browser snapshot/reload automation hung before controls could be
used. Consequently I did not claim that section switching, reference-plane
navigation, browser fetch, ZIP download, or stale-result clearing passed in
the browser. Repeat manually: switch between #47 and #3500; navigate to each
section plane; inspect the overview before choosing a bounded tissue patch;
fetch and download each ZIP; inspect the NIfTI shape, affine, bounds,
checksum and section metadata; then switch sections and confirm the second
export has no first-section metadata.

## Display regression follow-up

The registered overview provider can return an RGB display image, observed as
shape `(782, 900, 3)`. The previous overlay path passed that image to a
grayscale-only marker helper and raised `display overlay requires a 2-D
grayscale array`. The fix adds an explicit display-only grayscale/RGB adapter;
raw scientific arrays, pixel geometry and affines are unchanged. The focused
RGB regression test passes, and the full automated suite passes. The server
also responds with HTTP 200 on port 8513 and logs no provider-fetch or display
rendering exception during startup. Browser interaction remains unverified
because the browser connector hangs before controls can be exercised.

## Existing export inspection

The preserved `outputs/verified_patch/bigbrain_cutout_bundle.zip` contains
`bigbrain_crop.nii.gz`, `bigbrain_crop_preview.png`, and `metadata.json`.
The scientific image opened with nibabel as `uint8` shape `(251, 2, 251)`;
its finite range was `0..255`, voxel size
`[0.00800000038, 0.01999999955, 0.00800000038]` mm, and affine origin
`[-20.0, -0.87, -20.0]` mm. The NIfTI checksum matched metadata:
`5763aa082bed7237bf79baa9c64ce20557b704f3fbcef0b6401e341429be15bd`.
Metadata records requested bounds, actual geometry, provider padding,
software versions, license, and the reproduction command. The PNG is
visualization-only; raw scientific values remain in the NIfTI.

## UI behaviour and coverage

The main explorer now lists all metadata-discovered registered sections,
shows the selected section plane, and exposes a **Navigate to section plane**
action. For the current MRI Y location it lists nearby section planes with
their distances and distinguishes an intersecting plane from a nearby one.
Navigating to a nearby plane requires a separate explicit action and does not
claim that the nearby tissue is at the original MRI location.

Changing the selected section clears the previous section point, detailed
patch, and patch signature. The existing bounded preview, actual-resolution
reporting, affine/provenance export, and user annotation state for the active
crop are otherwise preserved.

Coverage is limited to the listed registered sections. The project does not
claim whole-brain cellular coverage, region names, or independent anatomical
review. The high-resolution provider remains reference-space placement only;
the external MRI registration setup is unchanged.

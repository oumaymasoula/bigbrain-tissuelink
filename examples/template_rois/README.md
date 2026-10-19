# Binary NIfTI ROI examples

This folder contains example inputs for the experimental template-ROI
workflow. A binary ROI is a 3-D mask: voxel value `1` means inside the selected
region and `0` means outside it. It is not a raw MRI scan.

## Preserved verified example

`cerebra_left_precentral_icbm2009c_sym_1mm_binary_roi.nii.gz`

- Region: CerebrA Precentral
- Hemisphere: left
- CerebrA label: 86
- Required template: ICBM 2009c nonlinear symmetric, 1 mm
- Shape: `193 × 229 × 193`
- Values: binary `0` and `1`
- Nonzero voxels: `21,393`
- SHA-256: `99b5ee39c809c4f187dfc193a6dc61ca862956bf4b86f6810933f4815885a098`
- Anatomical placement: awaiting independent review

Use **Load technically verified CerebrA example** in the application for this
example. That path uses the preserved transform and does not rerun it. The file
here is provided so the exact accepted input format is visible; uploading it
through the new-upload control would deliberately start a new container run
and is unnecessary.

## Preparing another ROI

Another file is accepted only if all of these are true:

1. It is a `.nii` or `.nii.gz` three-dimensional mask.
2. Its values are only `0` and `1`, with at least one voxel of each.
3. Its shape is exactly `193 × 229 × 193`.
4. Its voxel size is 1 mm and its affine is exactly the supported documented
   ICBM2009c nonlinear symmetric grid.
5. You have external provenance establishing its template identity. Matching
   dimensions and affine alone cannot prove the template.

Do not place raw T1 MRI, DICOM, patient scans, masks in another MNI template,
probability maps, or unverified files here.

## Additional upload-ready examples

These masks were extracted from the same preserved CerebrA atlas on the exact
supported grid. They are intentionally **not transformed yet**, so they can be
used to test the new-upload workflow without repeating the preserved
left-precentral transformation.

| Upload file | Region | Hemisphere | CerebrA label | Provenance |
|---|---|---:|---:|---|
| `cerebra_right_precentral_icbm2009c_sym_1mm_binary_roi.nii.gz` | Precentral | right | 35 | `cerebra_right_precentral_provenance.json` |
| `cerebra_left_postcentral_icbm2009c_sym_1mm_binary_roi.nii.gz` | Postcentral | left | 64 | `cerebra_left_postcentral_provenance.json` |
| `cerebra_right_cuneus_icbm2009c_sym_1mm_binary_roi.nii.gz` | Cuneus | right | 43 | `cerebra_right_cuneus_provenance.json` |

Upload **one NIfTI at a time**. In the application:

1. First use **Load technically verified CerebrA example** to enable uploads.
2. Keep the declared template set to **ICBM 2009c nonlinear symmetric
   (MNI152, tal_nlin_sym_09c), 1 mm**.
3. Check the explicit template-identification declaration.
4. Copy the corresponding provenance JSON content (or its identifying facts)
   into the **Template provenance** box.
5. Select the matching `.nii.gz` file and choose **Validate and transform
   uploaded ROI**.

Unlike the preserved example button, step 5 starts a new transform for the new
ROI. The red overlay means “voxels inside the ROI”; it does not mean an error,
disease, activation, or anatomical validation. Every new result remains
**Anatomical placement awaiting independent review**.

The reproducible extraction script is
`prepare_additional_cerebra_rois.py`. It refuses to overwrite existing files.

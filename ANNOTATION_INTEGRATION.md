# Annotation-tool integration feasibility

## Recommendation

Recommend **Labelme JSON** for the first and only planned integration. It is the smallest contract to consume: one image sidecar with polygon vertices, label names, and explicit image dimensions. The project does not currently integrate Labelme or any other annotation tool.

This recommendation is based on documented interchange simplicity, not on evidence that researchers require annotation support. No user study or researcher request was performed.

Official references:

- [Labelme repository and README](https://github.com/wkentaro/labelme)
- [Labelme polygon example](https://github.com/wkentaro/labelme/blob/main/examples/primitives/primitives.json)
- [Labelme source example loader](https://github.com/wkentaro/labelme/blob/main/examples/utils.py)
- [Labelme coordinate-order issue answered by the maintainer](https://github.com/wkentaro/labelme/issues/320)

## Candidate comparison

| Candidate | Installation / platform | Polygon and export format | Pixel convention / geometry | Coding | License and maintenance | Assessment |
|---|---|---|---|---|---|---|
| **Labelme** | Linux desktop; `pip install labelme`, GitHub install, or standalone app are documented in the [README](https://github.com/wkentaro/labelme#installation). | GUI polygons; native JSON sidecar with `shapes`, `points`, `shape_type`, `imagePath`, `imageHeight`, and `imageWidth`. JSON examples are in the [official repository](https://github.com/wkentaro/labelme/tree/main/examples). | The maintainer explicitly identifies points as `(x, y)` in [issue #320](https://github.com/wkentaro/labelme/issues/320). The example loader passes these directly to PIL drawing, so the practical raster convention is x right / y down from the top-left; the top-left statement is an implementation-based inference, not a separate formal coordinate-system specification. Image dimensions are stored and no import/export resampling is described. | No coding to draw/export; a small JSON parser is needed for integration. The current README says the on-disk JSON format and CLI are stable interfaces, while Python internals are not. | GPL-3.0. The public repository has active history and current v7.x documentation; v6.3.x is described as maintenance. | **Recommended**: lowest integration surface and directly matches a 2D PNG. |
| **QuPath** | Linux tarball is listed in the [official releases](https://github.com/qupath/qupath/releases) and installation documentation; Java desktop application. | GUI polygon annotations; GeoJSON, ImageJ ROI, and other exports are documented in [Exporting annotations](https://qupath.readthedocs.io/en/stable/docs/advanced/exporting_annotations.html). | QuPath explicitly documents shape export in pixel units with `(0,0)` at the top-left of the full-resolution image. It can preserve classifications and other properties in GeoJSON. Import/export should not resample vertices, but the exact image-server behavior for a plain PNG was not run here. | GUI drawing/export is possible; scripting is useful for repeatable batch export. | GPL-3.0. The [official repository](https://github.com/qupath/qupath) is actively developed and lists Linux releases. | Strong pathology tool, but GeoJSON carries a larger contract than needed and requires careful property/geometry validation. |
| **napari** | Linux desktop Python/Qt application; the [official README](https://github.com/napari/napari) documents virtual-environment installation and `pip install "napari[all]"`. | Shapes layer supports polygons; `layer.data` is a list of NumPy vertex arrays. The [Shapes API](https://napari.org/stable/api/napari.layers.Shapes.html) provides `save(path, plugin=...)`, but output format depends on an installed writer/plugin rather than one single core annotation JSON format. | Shapes use the same dimension ordering as image layers. The official API states image pixel locations are sample points centered in the rendered pixels and default units are pixels. No flip is automatically implied by loading a PNG. | GUI drawing is available; reliable interchange generally needs Python to inspect `layer.data` or select a writer. | BSD-3-Clause. The [official repository](https://github.com/napari/napari) shows active development and a large contributor ecosystem. | Excellent interactive viewer, but the format/plugin choice is less deterministic for a minimal upload page. |

Facts above are linked to official documentation or source repositories. The top-left interpretation for Labelme and the no-resampling statement for ordinary PNG handling are assumptions to be confirmed by an external round trip before production use.

## Feasibility result

The fixture was generated without downloading anything new from the existing validated crop:

- input: `outputs/ui_export/bigbrain_crop.nii.gz`
- section: `73c1fa55-d099-4854-8cda-c9a403c6080a--4427460c6af460478c6ce4cdb0264126` (#3458)
- coordinate space: `bigbrain` / BigBrain microscopic template (histology)
- selected source plane: `y=1`, `data[:, 1, :]`, the tissue-containing plane
- NIfTI shape: `(251, 2, 251)`; raw plane shape `(251, 251)` for `(x,z)`
- annotation image: `bigbrain_crop_y1_raw.png`, shape `(251,251)` as `(rows,columns)`
- exact mapping: annotation pixel `(u,v)` maps to NIfTI voxel `(i_x=v, i_y=1, i_z=u)`; this is a transpose only, with no flip
- raw values: unchanged `uint8`; no contrast adjustment, resize, or orientation metadata is applied to the annotation image

The asymmetric example polygon is stored in Labelme’s native JSON as:

```json
[[170, 170], [231, 181], [225, 222], [194, 236], [158, 211]]
```

All five vertices are inside the 251×251 image. Mapping them through the NIfTI affine produced the physical vertices recorded in `outputs/annotation_feasibility/mapping_report.json`. The overlay was inspected and the polygon crosses the visible tissue/background fissure boundary in the crop. This is a visual landmark description only, not an anatomical label.

The project environment does not contain the `labelme` executable, so no external Labelme GUI round trip was performed. The JSON is therefore a **clearly labelled native-format fixture**, not proof that a Labelme save/reopen cycle has passed. The fixture parser/mapping validation passed locally.

## Exact opening instructions

1. Extract [bigbrain_cutout_bundle.zip](outputs/ui_export/bigbrain_cutout_bundle.zip), or use the generated raw fixture directory [outputs/annotation_feasibility/](outputs/annotation_feasibility/).
2. Install Labelme in a separate environment, following the official instructions:

   ```bash
   python3 -m venv /tmp/labelme-env
   /tmp/labelme-env/bin/pip install labelme
   ```

3. Open the unchanged 2D image:

   ```bash
   /tmp/labelme-env/bin/labelme outputs/annotation_feasibility/bigbrain_crop_y1_raw.png \
     --output outputs/annotation_feasibility/labelme_user_annotations
   ```

4. Draw a polygon without resizing, rotating, or flipping the image. Save the JSON beside the same image. Labelme’s JSON `points` are `(x,y)` image pixels; preserve `imageWidth=251` and `imageHeight=251`.
5. An eventual Import annotations page must reject a JSON whose dimensions do not match the source image, and must display the overlay before accepting it.

The app now provides a **5. Import Labelme annotation** section with three required uploads: the Labelme JSON, `mapping_report.json`, and the original raw PNG. It validates the source section/coordinate space, source identity metadata, image filename and checksum, dimensions, grayscale PNG mode, finite in-bounds polygon vertices, polygon shape type, and the transpose-only/no-flip contract. Valid imports are shown on the unchanged annotation image, on an overlay copy, and on the current overview view; zooming or panning recomputes only the display placement and does not alter the mapped physical vertices. The app can download a provenance JSON containing the original pixel vertices, NIfTI voxel vertices, physical section vertices, labels, and transformation warning.

The raw PNG is scientific-value preserving for this uint8 plane, but the NIfTI remains authoritative for affine, section thickness, and physical coordinates.

## Smallest Import annotations plan

1. Add an “Import annotations” page that accepts Labelme JSON plus the matching raw 2D PNG, or a JSON sidecar linked to a known exported bundle.
2. Verify image dimensions, selected y-plane, section ID, and a checksum of the referenced image before rendering anything.
3. Parse only `shape_type="polygon"`; validate finite vertices and bounds; draw the pixel overlay without resampling.
4. Map `(u,v)` to `(i_x=v,i_y=selected_plane,i_z=u)` using the recorded transpose/flip contract, then show the polygon over the crop and its location on the overview.
5. Export the original Labelme JSON plus a project mapping report. Only emit physical vertices after the plane/affine mapping has been independently verified; do not claim registered 3D coordinates.

This plan deliberately excludes multiple tool formats, automatic segmentation, region search, and anatomical registration.

## Limitations

- The Labelme GUI round trip remains unperformed in this environment: the temporary environment contains the Labelme package, but its large Qt/runtime dependencies were not fully installed and this agent cannot operate a native desktop GUI. The real external polygon test therefore remains a manual check.
- The fixture’s “fissure-adjacent tissue” label is descriptive and not an anatomical identification.
- A 2D polygon on one histological plane is not automatically a 3D region.
- QuPath GeoJSON and napari writer formats were not imported; choosing either would require a separate format contract and tests.

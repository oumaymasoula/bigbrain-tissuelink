# Third-party notices

The MIT license in `LICENSE` applies only to original BigBrain TissueLink
source code and documentation where compatible. It does not relicense
third-party software or downloaded BigBrain data.

## Software dependencies

- [siibra-python](https://github.com/FZJ-INM1-BDA/siibra-python), pinned in
  `requirements.txt` as `1.0.1a25`. The upstream project is Apache-2.0.
- [Streamlit](https://github.com/streamlit/streamlit), BSD-3-Clause.
- [NumPy](https://github.com/numpy/numpy), BSD-3-Clause.
- [NiBabel](https://github.com/nipy/nibabel), MIT.
- [Pillow](https://github.com/python-pillow/Pillow), HPND.
- [pytest](https://github.com/pytest-dev/pytest), MIT.
- [streamlit-drawable-canvas](https://github.com/andfanilo/streamlit-drawable-canvas), MIT.
- [streamlit-image-coordinates](https://github.com/blackary/streamlit-image-coordinates), MIT.

Exact installed versions are environment-specific and should be captured with
`.venv/bin/pip freeze` when reproducing a local run.

## BigBrain data

BigBrain MRI, reconstructed histology and registered detailed sections are
external research data. Follow the current [BigBrain Project data and license
information](https://bigbrainproject.org/maps-and-models.html) and the source
record's attribution/non-commercial/share-alike terms. Do not apply the MIT
code license to those files or to generated exports containing them.

## BigBrainWarp

[BigBrainWarp](https://github.com/caseypaquola/BigBrainWarp) is an optional,
experimental external dependency for a future exact-template MRI workflow. Its
upstream repository is GPL-3.0; this project does not vendor or redistribute
its container, MINC2 installation, templates or transforms.

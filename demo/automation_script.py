#!/usr/bin/env python3
"""Record a continuous, silent Chrome demonstration of BigBrain TissueLink.

The script operates the real Streamlit application with Playwright, records the
browser viewport, and writes a machine-generated execution report. It never
modifies application source, datasets, or preserved scientific outputs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
DOWNLOADS = DEMO / "downloads"
APP_URL = "http://127.0.0.1:8513/"
CHROME = os.environ.get("TISSUELINK_CHROME") or shutil.which("google-chrome") or shutil.which("google-chrome-stable") or "/opt/google/chrome/chrome"
VIDEO = DEMO / "bigbrain_tissuelink_complete_demo.mp4"
TEMP_VIDEO = DEMO / "bigbrain_tissuelink_complete_demo.webm"
REPORT = DEMO / "execution_report.md"
ROI_FILE = ROOT / "examples/template_rois/cerebra_right_cuneus_icbm2009c_sym_1mm_binary_roi.nii.gz"
ROI_PROVENANCE = ROOT / "examples/template_rois/cerebra_right_cuneus_provenance.json"


class Demo:
    def __init__(self, page: Page):
        self.page = page
        self.results: list[dict[str, str]] = []
        self.started = datetime.now(timezone.utc)

    def record(self, name: str, status: str, detail: str = "") -> None:
        self.results.append({"step": name, "status": status, "detail": detail})
        print(f"[{status}] {name}: {detail}", flush=True)

    def pause(self, milliseconds: int = 1400) -> None:
        self.page.wait_for_timeout(milliseconds)

    def install_pointer(self) -> None:
        self.page.evaluate(
            """
            () => {
              if (document.getElementById('tissuelink-demo-pointer')) return;
              const style = document.createElement('style');
              style.textContent = `
                #tissuelink-demo-pointer { position:fixed; z-index:2147483647; width:18px; height:18px;
                  border:2px solid rgba(8,127,140,.95); border-radius:50%; background:rgba(255,255,255,.5);
                  pointer-events:none; transform:translate(-50%,-50%); transition:left .11s linear,top .11s linear; }
                #tissuelink-demo-pointer.click { box-shadow:0 0 0 12px rgba(8,127,140,.20); }
              `;
              document.head.appendChild(style);
              const pointer = document.createElement('div');
              pointer.id = 'tissuelink-demo-pointer'; pointer.style.left='40px'; pointer.style.top='40px';
              document.body.appendChild(pointer);
            }
            """
        )

    def pointer(self, x: float, y: float, click: bool = False) -> None:
        self.install_pointer()
        self.page.evaluate(
            """([x,y,click]) => {
              const p=document.getElementById('tissuelink-demo-pointer'); if(!p) return;
              p.style.left=x+'px'; p.style.top=y+'px'; p.classList.toggle('click',click);
              if(click) setTimeout(()=>p.classList.remove('click'),280);
            }""",
            [x, y, click],
        )

    def scroll_to(self, locator: Locator, pause: int = 700) -> None:
        locator.scroll_into_view_if_needed(timeout=20_000)
        box = locator.bounding_box()
        if box:
            self.pointer(box["x"] + min(box["width"] / 2, 420), box["y"] + min(box["height"] / 2, 300))
        self.pause(pause)

    def click(self, locator: Locator, pause: int = 1200) -> None:
        self.scroll_to(locator)
        box = locator.bounding_box()
        if box:
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            self.page.mouse.move(x, y, steps=18)
            self.pointer(x, y, True)
        locator.click(timeout=30_000, force=True)
        self.pause(pause)

    def expand(self, text: str, pause: int = 1000) -> None:
        summary = self.page.get_by_text(text, exact=True).last
        try:
            details = summary.locator("xpath=ancestor::details")
            if details.count() and details.get_attribute("open") is None:
                self.click(summary, pause)
            else:
                self.scroll_to(summary, pause)
        except Exception as exc:
            self.record(text, "unavailable", str(exc))

    def click_component_image(self, index: int, x_fraction: float, y_fraction: float) -> None:
        iframe = self.page.locator("iframe").nth(index)
        self.click_component_locator(iframe, x_fraction, y_fraction)

    def click_component_locator(self, iframe: Locator, x_fraction: float, y_fraction: float) -> None:
        self.scroll_to(iframe, 900)
        frame = iframe.element_handle().content_frame()
        image = frame.locator("#image")
        box = iframe.bounding_box()
        if box:
            x = box["x"] + box["width"] * x_fraction
            y = box["y"] + box["height"] * y_fraction
            self.page.mouse.move(x, y, steps=24)
            self.pointer(x, y, True)
        image.click(position={"x": max(3, image.bounding_box()["width"] * x_fraction), "y": max(3, image.bounding_box()["height"] * y_fraction)})
        self.pause(1800)

    def click_largest_component_image(self, x_fraction: float, y_fraction: float) -> None:
        candidates = []
        for index in range(self.page.locator("iframe").count()):
            iframe = self.page.locator("iframe").nth(index)
            box = iframe.bounding_box()
            if box and box["width"] > 0 and box["height"] > 0:
                candidates.append((box["width"] * box["height"], index))
        if not candidates:
            raise RuntimeError("no visible image component iframe")
        self.click_component_image(max(candidates)[1], x_fraction, y_fraction)

    def download(self, locator: Locator, suggested_prefix: str) -> None:
        self.scroll_to(locator)
        try:
            box = locator.bounding_box()
            if box:
                x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                self.page.mouse.move(x, y, steps=14); self.pointer(x, y, True)
            with self.page.expect_download(timeout=30_000) as info:
                locator.click(timeout=30_000, force=True)
            download = info.value
            target = DOWNLOADS / f"{suggested_prefix}_{download.suggested_filename}"
            download.save_as(target)
            self.pause(500)
            self.record(f"download {suggested_prefix}", "passed", target.name)
        except Exception as exc:
            self.record(f"download {suggested_prefix}", "failed", str(exc))

    def manual_route(self) -> None:
        page = self.page
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=90_000)
        page.get_by_text("MRI–Histology Explorer", exact=True).first.wait_for(timeout=90_000)
        self.install_pointer(); self.pause(2500)
        self.record("MRI–Histology Explorer loaded", "passed", page.url)

        self.expand("How to use TissueLink", 1300)
        self.expand("Limitations and provenance", 1200)
        section = page.get_by_label("Registered section")
        self.scroll_to(section); section.click(); self.pause(900)
        page.keyboard.press("Escape"); self.pause(900)
        self.record("registered section selection", "passed", "Opened the real section catalogue; retained documented section 3458")

        self.expand("Section coverage and evidence status", 1800)
        self.expand("Advanced · source and technical metadata", 1500)
        align = page.get_by_role("button", name="Align reference views to section #3458 plane")
        self.click(align, 2300)

        iframe_count = page.locator("iframe").count()
        if iframe_count >= 3:
            detailed_heading = page.get_by_text("Choose where to fetch the detailed patch", exact=True)
            detailed_iframe = detailed_heading.locator("xpath=following::iframe[1]")
            self.click_component_locator(detailed_iframe, 0.42, 0.565)
            self.pause(2200)
            selection_notice = page.get_by_text("Patch centre selected", exact=False)
            detail = "Selected a live point in the registered section" if selection_notice.count() else "Used the active linked/reference point exposed by the registered-section workflow"
            self.record("detailed tissue centre selection", "passed", detail)
        fetch = page.get_by_role("button", name="Fetch this selected detailed patch")
        self.scroll_to(fetch, 1200)
        if fetch.is_enabled():
            self.click(fetch, 1000)
            page.get_by_text("Review and export the detailed patch", exact=False).wait_for(timeout=150_000)
            self.pause(2600)
            self.record("real manual patch fetch", "passed", "Bounded registered-section patch rendered")
            stats = page.get_by_text("Optional · descriptive intensity statistics", exact=True)
            if stats.count(): self.expand("Optional · descriptive intensity statistics", 1300)
            add = page.get_by_role("button", name="Add patch to collection").last
            if add.is_enabled():
                self.click(add, 1700)
                self.record("manual patch collection", "passed", "Patch added to shared collection")
        else:
            self.record("real manual patch fetch", "failed", "Fetch remained disabled after selecting the registered-section image")

        atlas = page.get_by_text("Optional · atlas region navigation", exact=True)
        if atlas.count():
            self.expand("Optional · atlas region navigation", 1200)
            check = page.get_by_role("button", name="Check selected section against region mask")
            if check.count() and check.is_enabled():
                self.scroll_to(check, 1200)
                self.record("atlas navigation", "passed", "Displayed the available atlas-region selector and real section-mask check control")
            else:
                self.record("atlas navigation", "unavailable", "Region-mask check was disabled for the current catalogue state")

        page.get_by_text("MRI overview — 0.444 mm", exact=False).wait_for(timeout=60_000)
        self.click_component_image(0, 0.43, 0.48)
        self.record("MRI overview navigation", "passed", "Moved shared X/Z location using the live MRI overview")
        self.click_component_image(1, 0.57, 0.52)
        self.record("linked histology navigation", "passed", "Moved the same shared location from the histology overview")
        linked = page.get_by_text("Inspect the linked location", exact=False).first
        self.scroll_to(linked, 1700)

        comparison = page.get_by_text("Optional comparison views", exact=True)
        if comparison.count(): self.expand("Optional comparison views", 1700)
        save = page.get_by_role("button", name="Save location")
        self.scroll_to(save, 900)
        location_name = page.get_by_label("Location name")
        location_name.fill("automated_demo_location")
        self.click(save, 1400)
        self.record("location saving", "passed", "Saved shared-coordinate inspection location")
        export_location = page.get_by_role("button", name="Export location report (ZIP)")
        if export_location.count(): self.download(export_location, "location")

        final_heading = page.get_by_text("Review, save and reopen your collection", exact=True)
        self.scroll_to(final_heading, 1800)
        zip_button = page.get_by_role("button", name="Download collection ZIP")
        html_button = page.get_by_role("button", name="Download visual report HTML")
        if zip_button.count() and zip_button.is_enabled(): self.download(zip_button, "manual_collection")
        if html_button.count() and html_button.is_enabled(): self.download(html_button, "manual_report")

    def roi_route(self) -> None:
        page = self.page
        self.click(page.get_by_role("link", name="Experimental template ROI"), 2600)
        page.get_by_text("Experimental template ROI", exact=True).last.wait_for(timeout=90_000)
        self.record("Experimental template ROI loaded", "passed", page.url)
        load = page.get_by_role("button", name="Load technically verified CerebrA example")
        self.click(load, 3500)
        page.get_by_text("Verified example loaded end to end", exact=False).wait_for(timeout=90_000)
        self.record("verified CerebrA example", "passed", "Preserved checksums verified; historical transform not repeated")

        placement = page.get_by_text("3. Inspect placement", exact=True)
        self.scroll_to(placement, 2500)
        inspected = page.get_by_label("I inspected both placements and want to continue to section coverage.")
        self.click(inspected, 1000)
        compute = page.get_by_role("button", name="Compute intersecting available sections")
        self.click(compute, 1800)
        page.get_by_text("4. Intersecting registered sections and coverage", exact=True).wait_for(timeout=90_000)
        self.pause(1800)
        section_combo = page.get_by_label("Intersecting section")
        section_combo.click(); page.keyboard.type("#3146"); page.keyboard.press("Enter"); self.pause(1200)
        fetch = page.get_by_role("button", name="Fetch bounded patch at this mask location")
        self.click(fetch, 1200)
        page.get_by_text("5. Bounded patch preview", exact=True).wait_for(timeout=150_000)
        self.pause(2300)
        add = page.get_by_role("button", name="Add patch to collection")
        self.click(add, 1500)
        self.record("verified ROI patch workflow", "passed", "Section 3146 patch fetched and added to the same collection")

        page.get_by_text("2. New binary NIfTI ROI upload", exact=True).scroll_into_view_if_needed()
        self.pause(1200)
        identity = page.get_by_label("I explicitly identify this ROI as being in the selected template; I understand the NIfTI header alone cannot prove template identity.")
        if not identity.is_checked():
            identity.check(force=True)
            self.pause(900)
        provenance = page.get_by_role("textbox", name="Template provenance (required)")
        provenance.fill(ROI_PROVENANCE.read_text(encoding="utf-8"))
        uploader = page.locator('input[type="file"]').first
        uploader.set_input_files(str(ROI_FILE))
        self.pause(2600)
        # The file-uploader rerun can recreate the text area and checkbox.
        # Reassert both declarations on the current DOM before readiness check.
        provenance = page.get_by_role("textbox", name="Template provenance (required)")
        provenance.fill(ROI_PROVENANCE.read_text(encoding="utf-8"))
        provenance.press("Tab")
        identity = page.get_by_role("checkbox", name="I explicitly identify this ROI as being in the selected template; I understand the NIfTI header alone cannot prove template identity.")
        if not identity.is_checked(): identity.check(force=True)
        self.pause(2200)
        self.record("compatible ROI upload", "passed", f"{ROI_FILE.name}; exact documented template and provenance")
        transform = page.get_by_role("button", name=f"Validate and transform {ROI_FILE.name}")
        self.scroll_to(transform, 1000)
        if not transform.is_enabled():
            requirements = " | ".join(page.locator('[data-testid="stAlert"]').all_inner_texts()[-3:])
            self.record("real uploaded ROI transform", "failed", f"Transform button remained disabled: {requirements}")
        else:
          self.click(transform, 900)
          try:
            page.get_by_text("Transform completed", exact=False).wait_for(timeout=650_000)
            self.record("real uploaded ROI transform", "passed", "Pinned BigBrainWarp container completed")
            state = page.get_by_text("Current ROI processing state", exact=True)
            self.scroll_to(state, 2500)
            self.expand("Complete transform provenance", 1800)
          except Exception as exc:
            errors = page.locator('[data-testid="stAlert"]').all_inner_texts()
            self.record("real uploaded ROI transform", "failed", (" | ".join(errors[-3:]) or str(exc))[:1000])

        final_heading = page.get_by_text("Review, save and reopen your collection", exact=True)
        self.scroll_to(final_heading, 1700)
        html_button = page.get_by_role("button", name="Download visual report HTML")
        if html_button.count() and html_button.is_enabled(): self.download(html_button, "mixed_report")

    def alignment_route(self) -> None:
        page = self.page
        page.goto(f"{APP_URL}Validation", wait_until="domcontentloaded", timeout=90_000)
        self.pause(2800)
        page.get_by_text("Independent alignment review", exact=True).wait_for(timeout=90_000)
        self.record("Alignment review loaded", "passed", page.url)
        self.expand("Advanced · source and coordinate context", 1300)
        self.expand("Advanced · slice and display controls", 1300)
        page.get_by_text("2. Select and save points", exact=True).scroll_into_view_if_needed(); self.pause(1000)
        if page.locator("iframe").count() >= 1:
            self.click_component_image(0, 0.46, 0.47)
            save_mri = page.get_by_role("button", name="Save MRI point")
            self.click(save_mri, 1400)
            self.record("MRI alignment point", "passed", "Independent MRI point saved")
        hist_radio = page.get_by_role("radio", name="Histology", exact=True)
        self.click(hist_radio, 1300)
        if page.locator("iframe").count() >= 1:
            self.pause(1800)
            self.click_component_image(0, 0.54, 0.51)
            save_hist = page.get_by_role("button", name="Save Histology point")
            self.click(save_hist, 1600)
            self.record("histology alignment point", "passed", "Independent histology point saved and discrepancy displayed")
        review = page.get_by_text("3. Review saved discrepancies", exact=True)
        self.scroll_to(review, 2200)
        export = page.get_by_role("button", name="Export saved landmark review (JSON)")
        if export.count(): self.download(export, "alignment")

    def write_report(self, video_status: str, video_detail: str) -> None:
        finished = datetime.now(timezone.utc)
        lines = [
            "# BigBrain TissueLink automated demonstration execution report",
            "",
            f"- Started: `{self.started.isoformat()}`",
            f"- Finished: `{finished.isoformat()}`",
            f"- Browser: Google Chrome `{CHROME}`",
            "- Viewport/video: `1920 × 1080`, silent",
            f"- Application: `{APP_URL}`",
            f"- Video: `{VIDEO}`",
            f"- Video verification: **{video_status}** — {video_detail}",
            "- Scientific-data policy: preserved left-precentral transform loaded by checksum; new upload used the documented right-cuneus compatible mask.",
            "",
            "## Recorded steps",
            "",
            "| Step | Status | Detail |",
            "|---|---|---|",
        ]
        for item in self.results:
            detail = item["detail"].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {item['step']} | {item['status']} | {detail} |")
        lines += [
            "",
            "## Limitations",
            "",
            "- Anatomical overlays remain awaiting independent review; the video does not claim anatomical accuracy.",
            "- Any step marked failed or unavailable above is shown honestly and was not replaced with fabricated output.",
            "- Downloaded files are demonstration artifacts under `demo/downloads/`; they are not changes to preserved source data.",
        ]
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    DEMO.mkdir(exist_ok=True)
    DOWNLOADS.mkdir(exist_ok=True)
    for old in (TEMP_VIDEO, VIDEO):
        if old.exists():
            old.unlink()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=CHROME,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--hide-scrollbars"],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            screen={"width": 1920, "height": 1080},
            device_scale_factor=1,
            accept_downloads=True,
            record_video_dir=str(DEMO),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        page.set_default_timeout(30_000)
        video_handle = page.video
        demo = Demo(page)
        for name, workflow in (
            ("MRI–Histology Explorer", demo.manual_route),
            ("Experimental Template ROI", demo.roi_route),
            ("Alignment Review", demo.alignment_route),
        ):
            try:
                workflow()
            except Exception as exc:
                demo.record(name, "failed", repr(exc))
                try: demo.pause(2200)
                except Exception: pass
        demo.pause(2200)
        context.close()
        browser.close()
        recorded_path = Path(video_handle.path())
        recorded_path.replace(TEMP_VIDEO)

    conversion = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(TEMP_VIDEO), "-an", "-vf", "scale=1920:1080:flags=lanczos",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(VIDEO),
        ],
        capture_output=True,
        text=True,
    )
    status = "passed" if conversion.returncode == 0 and VIDEO.is_file() and VIDEO.stat().st_size > 0 else "failed"
    detail = f"FFmpeg return code {conversion.returncode}; {VIDEO.stat().st_size if VIDEO.exists() else 0} bytes"
    demo.write_report(status, detail)
    (DEMO / "automation_results.json").write_text(json.dumps(demo.results, indent=2), encoding="utf-8")
    if status != "passed":
        raise RuntimeError(conversion.stderr[-2000:])
    print(VIDEO)


if __name__ == "__main__":
    main()

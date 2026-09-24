"""Appearance assets must stay lightweight and fail clearly without an encoder."""

import os
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree

from tools.icons import _svg, orb_lines

ROOT = Path(__file__).resolve().parents[1]


def test_video_cli_reports_missing_ffmpeg():
    environment = os.environ.copy()
    environment["PATH"] = ""
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "render.py"), "--video", "magnificent-spider"],
        cwd=ROOT, env=environment, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "--video requires ffmpeg on PATH" in result.stderr
    assert result.stdout == ""


def test_favicon_is_a_valid_lightweight_source_orb():
    image = _svg(orb_lines())
    assert len(image) <= 10 * 1024
    svg = ElementTree.fromstring(image)
    assert svg.tag == "{http://www.w3.org/2000/svg}svg"
    assert any(element.tag.endswith("path") and "L" in element.attrib.get("d", "")
               for element in svg)

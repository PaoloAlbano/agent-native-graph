"""Link previews are static, page-specific, repeatable and independent of inference."""

import importlib.util
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "social_preview", ROOT / "docs/site/social_preview.py"
)
preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)


def page(path, title="ANA &amp; results"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "<html><head><title>" + title + '</title><meta name="description" '
        'content="Tools &amp; research"></head><body>Content</body></html>',
        encoding="utf-8",
    )


def test_previews_are_static_page_specific_and_idempotent(tmp_path):
    home = tmp_path / "index.html"
    nested = tmp_path / "runs" / "model name.html"
    page(home)
    page(nested, "A different run")
    assert preview.add_social_previews(tmp_path) == 2
    first = home.read_text()
    assert '<meta property="og:title" content="ANA &amp; results">' in first
    assert '<meta property="og:description" content="Tools &amp; research">' in first
    assert f'property="og:url" content="{preview.PUBLIC_URL}"' in first
    assert f"{preview.PUBLIC_URL}runs/model%20name.html" in nested.read_text()
    assert 'name="twitter:card" content="summary_large_image"' in first
    assert first.index('property="og:image"') < first.index("</head>")
    assert preview.add_social_previews(tmp_path) == 2
    assert home.read_text() == first
    image = (tmp_path / "assets" / preview.IMAGE).read_bytes()
    assert image == (ROOT / "docs/site" / preview.IMAGE).read_bytes()
    assert image[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", image[16:24]) == (1200, 630)


def test_fork_url_override(tmp_path):
    page(tmp_path / "index.html")
    preview.add_social_previews(tmp_path, "https://example.org/project")
    html = (tmp_path / "index.html").read_text()
    assert 'content="https://example.org/project/"' in html
    assert 'content="https://example.org/project/assets/ana-social-preview.png"' in html
    assert preview.PUBLIC_URL not in html


@pytest.mark.parametrize(
    "url",
    [
        "/relative",
        "file:///tmp/site",
        "https://user:secret@example.org",
        "https://example.org/?x=1",
        "https://example.org/#section",
    ],
)
def test_invalid_public_url_rejected(tmp_path, url):
    page(tmp_path / "index.html")
    with pytest.raises(ValueError, match="absolute HTTP"):
        preview.add_social_previews(tmp_path, url)


def test_missing_build_fails(tmp_path):
    with pytest.raises(ValueError, match="No generated HTML"):
        preview.add_social_previews(tmp_path)


def test_html_fragment_is_not_a_publishable_page(tmp_path):
    (tmp_path / "index.html").write_text("<p>No head</p>")
    with pytest.raises(ValueError, match="no closing head"):
        preview.add_social_previews(tmp_path)

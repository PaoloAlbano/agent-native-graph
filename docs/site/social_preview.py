"""Add static link-preview metadata after the research website is generated."""

import argparse
import re
import shutil
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlsplit

PUBLIC_URL = "https://paoloalbano.github.io/agent-native-graph/"
IMAGE = "ana-social-preview.png"
IMAGE_ALT = "ana - Agent-Native APIs"
START = "<!-- ANA social preview -->"
END = "<!-- /ANA social preview -->"


class PageMetadata(HTMLParser):
    """Read the generated page's title and description without running JavaScript."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title = ""
        self.description = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta" and attrs.get("name", "").lower() == "description":
            self.description = attrs.get("content", "")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def add_social_previews(site_dir: Path, base_url: str = PUBLIC_URL) -> int:
    """Package the shared logo and add an idempotent metadata block to every page."""
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use an absolute HTTP(S) site URL without credentials, query or fragment")
    base_url = base_url.rstrip("/") + "/"
    pages = sorted(site_dir.rglob("*.html"))
    if not pages:
        raise ValueError(f"No generated HTML pages in {site_dir}")
    image_url = base_url + "assets/" + IMAGE
    for page in pages:
        document = page.read_text(encoding="utf-8")
        document = re.sub(
            re.escape(START) + r".*?" + re.escape(END) + r"\n?",
            "",
            document,
            flags=re.DOTALL,
        )
        closing_head = re.search(r"</head\s*>", document, flags=re.IGNORECASE)
        if closing_head is None:
            raise ValueError(f"Generated page has no closing head: {page}")
        metadata = PageMetadata()
        metadata.feed(document[: closing_head.start()])
        relative = page.relative_to(site_dir).as_posix()
        page_url = base_url + ("" if relative == "index.html" else quote(relative, safe="/"))
        title = metadata.title.strip() or "Agent-Native APIs"
        description = metadata.description or "Rethinking data access for LLM agents."
        tags = {
            "og:type": "website",
            "og:site_name": "Agent-Native APIs",
            "og:title": title,
            "og:description": description,
            "og:url": page_url,
            "og:image": image_url,
            "og:image:type": "image/png",
            "og:image:width": "1200",
            "og:image:height": "630",
            "og:image:alt": IMAGE_ALT,
            "twitter:card": "summary_large_image",
            "twitter:title": title,
            "twitter:description": description,
            "twitter:image": image_url,
            "twitter:image:alt": IMAGE_ALT,
        }
        lines = [START]
        for key, value in tags.items():
            attribute = "property" if key.startswith("og:") else "name"
            lines.append(f'<meta {attribute}="{key}" content="{escape(value, quote=True)}">')
        lines.append(END)
        position = closing_head.start()
        document = document[:position] + "\n".join(lines) + "\n" + document[position:]
        page.write_text(document, encoding="utf-8")
    assets = site_dir / "assets"
    assets.mkdir(exist_ok=True)
    shutil.copyfile(Path(__file__).with_name(IMAGE), assets / IMAGE)
    return len(pages)


def main():
    """Package social previews for the default Pages URL or a fork/custom domain."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, required=True)
    parser.add_argument("--base-url", default=PUBLIC_URL)
    args = parser.parse_args()
    count = add_social_previews(args.site_dir, args.base_url)
    print(f"Added ANA social previews to {count} pages")


if __name__ == "__main__":
    main()

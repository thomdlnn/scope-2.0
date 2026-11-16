"""Rendu Markdown sans HTML brut.

Le HTML écrit dans un rapport est affiché tel quel (échappé), jamais
interprété, et les liens ne peuvent pointer que vers http(s), mailto ou des
ancres/chemins relatifs.
"""

from __future__ import annotations

import re

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

SAFE_URL = re.compile(r"^(https?:|mailto:|#|/(?!/)|\.{1,2}/|[^:/?#]+(?:[/?#]|$))", re.I)


class _SanitizeUrls(Treeprocessor):
    def run(self, root):
        for el in root.iter():
            for attr in ("href", "src"):
                val = el.get(attr)
                if val is not None and not SAFE_URL.match(val.strip()):
                    del el.attrib[attr]
            if el.tag == "a" and el.get("href", "").startswith(("http:", "https:")):
                el.set("rel", "noopener noreferrer")
                el.set("target", "_blank")


class _NoRawHtml(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")
        md.treeprocessors.register(_SanitizeUrls(md), "sanitize_urls", 0)


def render_markdown(text: str | None) -> str:
    if not text:
        return ""
    md = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists", _NoRawHtml()])
    return md.convert(text)

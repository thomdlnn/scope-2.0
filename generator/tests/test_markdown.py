from scope_gen.markdown_safe import render_markdown


def test_html_brut_echappe():
    html = render_markdown('avant <script>alert("x")</script> après\n\n<div onclick="x">bloc</div>')
    assert "<script>" not in html and "<div" not in html
    assert "&lt;script&gt;" in html and "&lt;div" in html


def test_liens_dangereux_neutralises():
    html = render_markdown("[a](javascript:alert(1)) [b](//evil.example) [c](https://ok.example) [d](docs/x.md)")
    assert "javascript:" not in html
    assert "//evil.example" not in html
    assert 'href="https://ok.example"' in html
    assert 'href="docs/x.md"' in html


def test_markdown_rendu():
    html = render_markdown("- **gras**\n- `code`\n\n| a | b |\n| - | - |\n| 1 | 2 |")
    assert "<strong>gras</strong>" in html and "<code>code</code>" in html and "<table>" in html

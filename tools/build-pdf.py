#!/usr/bin/env python3
"""
Minimal Markdown → HTML converter tailored for the PraxisZeit setup guide.
Handles: headings, paragraphs, GitHub-style tables, fenced code blocks,
inline code, bold/italic, lists (ul/ol), task checkboxes, blockquotes,
horizontal rules, links. No external deps.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path


_HERE = Path(__file__).parent
SRC = _HERE / (sys.argv[1] if len(sys.argv) > 1 else "setup.md")
OUT_HTML = _HERE / (sys.argv[2] if len(sys.argv) > 2 else "setup.html")
_TITLE = sys.argv[3] if len(sys.argv) > 3 else "setup"


CSS = r"""
@page {
  size: A4;
  margin: 18mm 16mm 22mm 16mm;
  @bottom-center {
    content: "PraxisZeit __DOCTITLE__ · v1.4.3 · Seite " counter(page) " / " counter(pages);
    font-size: 8pt; color: #777;
  }
}

html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }

body {
  font-family: "Inter", "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 10.5pt;
  line-height: 1.5;
  color: #1a1a1a;
  margin: 0;
}

h1, h2, h3, h4 {
  font-weight: 700;
  color: #0b3d91;
  line-height: 1.25;
  margin-top: 1.4em;
  margin-bottom: 0.5em;
}
h1 { font-size: 26pt; border-bottom: 3px solid #0b3d91; padding-bottom: 6pt; page-break-before: avoid; }
h2 { font-size: 17pt; border-bottom: 1px solid #d0d7de; padding-bottom: 3pt; margin-top: 1.6em; page-break-after: avoid; }
h3 { font-size: 13pt; color: #1f4f9e; page-break-after: avoid; }
h4 { font-size: 11pt; color: #333; }

h2 + p, h3 + p { page-break-before: avoid; }

p { margin: 0.5em 0; }

strong { color: #0b3d91; font-weight: 700; }

a { color: #0b66c4; text-decoration: none; word-break: break-all; }
a:hover { text-decoration: underline; }

hr {
  border: none;
  border-top: 1px solid #d0d7de;
  margin: 1.6em 0;
}

ul, ol { padding-left: 1.5em; margin: 0.5em 0; }
li { margin: 0.18em 0; }
li input[type="checkbox"] { margin-right: 0.4em; transform: translateY(1px); }

blockquote {
  border-left: 4px solid #f0b800;
  background: #fff8e1;
  padding: 8pt 12pt;
  margin: 0.8em 0;
  color: #5a4400;
  page-break-inside: avoid;
  border-radius: 0 4px 4px 0;
}
blockquote p:first-child { margin-top: 0; }
blockquote p:last-child { margin-bottom: 0; }

code {
  font-family: "JetBrains Mono", "Fira Mono", Consolas, monospace;
  font-size: 9pt;
  background: #f3f4f6;
  border: 1px solid #e3e6ea;
  border-radius: 3px;
  padding: 1px 4px;
  color: #b03060;
  word-break: break-word;
}

pre {
  background: #0f172a;
  color: #e2e8f0;
  padding: 10pt 12pt;
  border-radius: 4px;
  font-family: "JetBrains Mono", "Fira Mono", Consolas, monospace;
  font-size: 8.6pt;
  line-height: 1.42;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  page-break-inside: avoid;
  margin: 0.6em 0;
}
pre code {
  background: transparent;
  border: 0;
  padding: 0;
  color: inherit;
  font-size: inherit;
}

table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.8em 0;
  font-size: 9.5pt;
  page-break-inside: avoid;
}
th, td {
  border: 1px solid #d0d7de;
  padding: 5pt 7pt;
  text-align: left;
  vertical-align: top;
}
th {
  background: #0b3d91;
  color: white;
  font-weight: 600;
}
tr:nth-child(even) td { background: #f6f8fa; }

.titlepage {
  text-align: center;
  padding: 60mm 0 0 0;
  page-break-after: always;
}
.titlepage h1 {
  font-size: 36pt;
  border: 0;
  margin-bottom: 0.2em;
}
.titlepage .subtitle {
  font-size: 14pt;
  color: #555;
  margin-bottom: 1.5em;
}
.titlepage .version {
  font-size: 12pt;
  color: #0b3d91;
  font-weight: 600;
}
.titlepage .meta {
  margin-top: 8em;
  font-size: 10pt;
  color: #888;
}

/* Avoid orphaned headings */
h1, h2, h3, h4 { page-break-after: avoid; }
table, pre, blockquote { page-break-inside: avoid; }
"""


# ----------- helpers -----------

INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
AUTOLINK_RE = re.compile(r"<(https?://[^>]+)>")


def inline(text: str) -> str:
    """Apply inline markdown rules. Order matters: code first so its content is preserved."""
    placeholders: list[str] = []

    def stash(match: re.Match) -> str:
        placeholders.append(html.escape(match.group(1)))
        return f"\x00CODE{len(placeholders) - 1}\x00"

    text = INLINE_CODE_RE.sub(stash, text)
    text = html.escape(text, quote=False)
    text = AUTOLINK_RE.sub(r'<a href="\1">\1</a>', text)
    text = LINK_RE.sub(r'<a href="\2">\1</a>', text)
    text = BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = ITALIC_RE.sub(r"<em>\1</em>", text)

    def restore(match: re.Match) -> str:
        idx = int(match.group(1))
        return f"<code>{placeholders[idx]}</code>"

    text = re.sub(r"\x00CODE(\d+)\x00", restore, text)
    return text


def render_table(lines: list[str]) -> str:
    """lines = [header, separator, ...rows]. Pipes assumed."""

    def split_row(row: str) -> list[str]:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        return cells

    headers = split_row(lines[0])
    rows = [split_row(r) for r in lines[2:]]
    out = ["<table>", "<thead><tr>"]
    out.extend(f"<th>{inline(h)}</th>" for h in headers)
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def is_table_separator(line: str) -> bool:
    if "|" not in line:
        return False
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return all(re.fullmatch(r":?-+:?", c or "") for c in cells) and cells


def parse(md: str) -> str:
    lines = md.splitlines()
    i = 0
    out: list[str] = []
    in_list = False
    list_tag = "ul"

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append(f"</{list_tag}>")
            in_list = False

    para: list[str] = []

    def flush_para() -> None:
        if para:
            joined = " ".join(para).strip()
            if joined:
                out.append(f"<p>{inline(joined)}</p>")
            para.clear()

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()

        # fenced code block
        if line.lstrip().startswith("```"):
            flush_para()
            close_list()
            i += 1
            code_lines: list[str] = []
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            code_html = html.escape("\n".join(code_lines))
            out.append(f"<pre><code>{code_html}</code></pre>")
            continue

        # blank line
        if not line.strip():
            flush_para()
            close_list()
            i += 1
            continue

        # heading
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_para()
            close_list()
            level = len(m.group(1))
            text = m.group(2).rstrip("#").strip()
            out.append(f"<h{level}>{inline(text)}</h{level}>")
            i += 1
            continue

        # horizontal rule
        if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", line.strip()):
            flush_para()
            close_list()
            out.append("<hr>")
            i += 1
            continue

        # table: header line followed by separator
        if "|" in line and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
            flush_para()
            close_list()
            tbl = [line, lines[i + 1]]
            j = i + 2
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                tbl.append(lines[j])
                j += 1
            out.append(render_table(tbl))
            i = j
            continue

        # blockquote
        if line.lstrip().startswith(">"):
            flush_para()
            close_list()
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                quote_lines.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = parse("\n".join(quote_lines))
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # unordered list (incl. task items)
        m_ul = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        m_ol = re.match(r"^(\s*)(\d+)\.\s+(.*)$", line)

        if m_ul or m_ol:
            flush_para()
            new_tag = "ul" if m_ul else "ol"
            if in_list and list_tag != new_tag:
                close_list()
            if not in_list:
                out.append(f"<{new_tag}>")
                in_list = True
                list_tag = new_tag

            content = (m_ul or m_ol).group(2 if m_ul else 3)
            task = re.match(r"^\[( |x|X)\]\s+(.*)$", content)
            if task:
                checked = "checked" if task.group(1).lower() == "x" else ""
                out.append(
                    f'<li style="list-style:none; margin-left:-1.2em;">'
                    f'<input type="checkbox" {checked} disabled> {inline(task.group(2))}</li>'
                )
            else:
                out.append(f"<li>{inline(content)}</li>")
            i += 1
            continue

        # default: paragraph text
        close_list()
        para.append(line.strip())
        i += 1

    flush_para()
    close_list()
    return "\n".join(out)


def build_titlepage() -> str:
    if _TITLE == "review":
        return """
<section class="titlepage">
  <h1>PraxisZeit</h1>
  <div class="subtitle">Voll-Audit &middot; Security &amp; ArbZG-Compliance</div>
  <div class="version">Version 1.4.3</div>
  <div class="meta">
    Branch master &middot; HEAD 5e03cdf<br>
    Auditdatum: 23. Mai 2026<br><br>
    <em>Letztes Audit: 08. April 2026 &middot; Delta + Voll-Audit</em>
  </div>
</section>
"""
    return """
<section class="titlepage">
  <h1>PraxisZeit</h1>
  <div class="subtitle">Installations- &amp; Setup-Anleitung<br>für Linux und Windows</div>
  <div class="version">Version 1.4.3</div>
  <div class="meta">
    Native Installation (ohne Docker) &middot; Docker-Deployment<br>
    Stand: 23. Mai 2026<br><br>
    <em>Konform mit ArbZG &sect; 16 (2-Jahres-Aufbewahrung) und DSGVO</em>
  </div>
</section>
"""


def main() -> int:
    md = SRC.read_text(encoding="utf-8")
    # Drop the first H1 + first separator since the title page replaces them
    md = re.sub(r"^# [^\n]+\n+(?:[^\n]+\n+){0,4}---\n", "", md, count=1, flags=re.MULTILINE)

    body = parse(md)

    doc_title = "Voll-Audit" if _TITLE == "review" else "Setup-Anleitung"
    page_css = CSS.replace("__DOCTITLE__", doc_title)

    html_doc = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>PraxisZeit {doc_title} v1.4.3</title>
<style>{page_css}</style>
</head>
<body>
{build_titlepage()}
{body}
</body>
</html>
"""

    OUT_HTML.write_text(html_doc, encoding="utf-8")
    print(f"wrote {OUT_HTML} ({len(html_doc):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

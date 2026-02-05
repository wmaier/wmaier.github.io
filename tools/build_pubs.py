#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import html
import re


ROOT = Path(__file__).resolve().parents[1]
BIB_DIR = ROOT / "pub" / "bib"
ALL_BIB_PATH = BIB_DIR / "all.pub"
ALL_BIB_COMPAT = BIB_DIR / "all.bib"
INDEX_PATH = ROOT / "index.html"


LATEX_MAP = {
    "\\\"a": "ä",
    "\\\"o": "ö",
    "\\\"u": "ü",
    "\\\"A": "Ä",
    "\\\"O": "Ö",
    "\\\"U": "Ü",
    "\\'a": "á",
    "\\'e": "é",
    "\\'i": "í",
    "\\'o": "ó",
    "\\'u": "ú",
    "\\`a": "à",
    "\\`e": "è",
    "\\`i": "ì",
    "\\`o": "ò",
    "\\`u": "ù",
    "\\^a": "â",
    "\\^e": "ê",
    "\\^i": "î",
    "\\^o": "ô",
    "\\^u": "û",
    "\\~n": "ñ",
    "\\ss": "ß",
}

LATEX_PATTERN = re.compile(r"\\['`^\"~][A-Za-z]|\\ss|\\c\{?[A-Za-z]\}?")


def latex_to_unicode(text: str) -> str:
    # unwrap braces around latex commands like {\"u} or {\c{c}}
    text = re.sub(r'\{(\\\\[^{}]+)\}', r'\1', text)
    # normalize brace-wrapped accents like \"{u}
    text = re.sub(r'\\\\([\'`^\"~])\{([A-Za-z])\}', r'\\\1\2', text)
    # direct replacements for remaining accent commands
    for key, value in LATEX_MAP.items():
        text = text.replace(key, value)

    # handle common accent commands without braces, e.g. \"u, \'e
    def accent_repl(match: re.Match) -> str:
        cmd = match.group(1)
        char = match.group(2)
        key = f"\\{cmd}{char}"
        return LATEX_MAP.get(key, match.group(0))

    text = re.sub(r'\\([\'`^\"~])([A-Za-z])', accent_repl, text)
    def repl(match: re.Match) -> str:
        token = match.group(0)
        if token.startswith(r"\c"):
            return "ç"
        return LATEX_MAP.get(token, token)

    text = LATEX_PATTERN.sub(repl, text)
    # final pass for any remaining accent commands
    def final_repl(match: re.Match) -> str:
        key = "\\" + match.group(1) + match.group(2)
        return LATEX_MAP.get(key, match.group(0))

    text = re.sub(r'\\([\'`^\"~])([A-Za-z])', final_repl, text)
    # last-resort replacement for any lingering \"u-style sequences
    text = re.sub(r'\\\"([A-Za-z])', lambda m: LATEX_MAP.get('\\\"' + m.group(1), m.group(0)), text)
    text = text.replace("{", "").replace("}", "")
    text = text.replace("\\&", "&")
    return text


def parse_bibtex_entries(bib: str) -> list[dict]:
    entries = []
    i = 0
    while True:
        at = bib.find("@", i)
        if at == -1:
            break
        j = bib.find("{", at)
        if j == -1:
            break
        entry_type = bib[at + 1 : j].strip().lower()
        k = bib.find(",", j)
        if k == -1:
            break
        key = bib[j + 1 : k].strip()
        depth = 1
        idx = k + 1
        while idx < len(bib) and depth > 0:
            if bib[idx] == "{":
                depth += 1
            elif bib[idx] == "}":
                depth -= 1
            idx += 1
        entry_body = bib[k + 1 : idx - 1].strip()
        raw_entry = bib[at:idx]
        fields: dict[str, str] = {}
        pos = 0
        while pos < len(entry_body):
            while pos < len(entry_body) and entry_body[pos] in " \t\n,":
                pos += 1
            if pos >= len(entry_body):
                break
            m = re.match(r"([a-zA-Z0-9_\-]+)\s*=", entry_body[pos:])
            if not m:
                break
            field = m.group(1).lower()
            pos += m.end()
            while pos < len(entry_body) and entry_body[pos].isspace():
                pos += 1
            if pos >= len(entry_body):
                break
            if entry_body[pos] == "{":
                depth = 1
                pos += 1
                start = pos
                while pos < len(entry_body) and depth > 0:
                    if entry_body[pos] == "{":
                        depth += 1
                    elif entry_body[pos] == "}":
                        depth -= 1
                    pos += 1
                value = entry_body[start : pos - 1]
            elif entry_body[pos] == "\"":
                pos += 1
                start = pos
                while pos < len(entry_body) and entry_body[pos] != "\"":
                    pos += 1
                value = entry_body[start:pos]
                pos += 1
            else:
                start = pos
                while pos < len(entry_body) and entry_body[pos] not in ",\n":
                    pos += 1
                value = entry_body[start:pos].strip()
            fields[field] = value.strip()
        entries.append({"type": entry_type, "key": key, "fields": fields, "raw": raw_entry})
        i = idx
    return entries


def format_authors(author_str: str) -> str:
    parts = [a.strip() for a in author_str.replace("\n", " ").split(" and ") if a.strip()]
    out = []
    for part in parts:
        if "," in part:
            last, first = [x.strip() for x in part.split(",", 1)]
            name = (first + " " + last).strip()
        else:
            name = part
        out.append(name)
    return ", ".join(out)


def field(entry: dict, name: str) -> str:
    value = latex_to_unicode(entry["fields"].get(name, "")).strip()
    # last cleanup for any remaining accent sequences
    value = re.sub(r'\\([\'`^\"~])([A-Za-z])', lambda m: LATEX_MAP.get('\\' + m.group(1) + m.group(2), m.group(0)), value)
    # Use typographic en dash in display text (TeX --)
    value = value.replace("--", "–")
    return value


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def build_pubs_html(entries: list[dict]) -> str:
    by_year: dict[str, list[dict]] = {}
    for e in entries:
        year = e["fields"].get("year", "").strip()
        if not year:
            continue
        by_year.setdefault(year, []).append(e)

    years = sorted(by_year.keys(), key=lambda y: int(re.sub(r"\D", "", y) or 0), reverse=True)

    items_html: list[str] = []
    for y in years:
        items_html.append(f'<details class="pub-year" open>')
        items_html.append(f"  <summary>{esc(y)}</summary>")
        items_html.append('  <div class="pubyear">')
        for e in by_year[y]:
            title = field(e, "title")
            authors = field(e, "author") or field(e, "editor")
            authors = format_authors(authors) if authors else ""

            venue = ""
            if e["type"] == "article":
                journal = field(e, "journal")
                volume = field(e, "volume")
                number = field(e, "number")
                venue = journal
                if volume:
                    venue += f" {volume}"
                    if number:
                        venue += f"({number})"
            elif e["type"] in ("inproceedings", "incollection", "conference"):
                venue = field(e, "booktitle")
            elif e["type"] == "book":
                venue = field(e, "publisher") or field(e, "booktitle")
            else:
                venue = field(e, "booktitle") or field(e, "journal")

            address = field(e, "address")
            pages = field(e, "pages")

            links: list[str] = []
            for label, fname in [
                ("pdf", "pdf"),
                ("pdf (preprint)", "pdfpreprint"),
                ("pdf (errata)", "pdferrata"),
                ("url", "url"),
                ("code", "code"),
            ]:
                url = e["fields"].get(fname, "")
                if url:
                    links.append(f'<a href="{esc(url)}">[{esc(label)}]</a>')

            doi = e["fields"].get("doi", "")
            if doi:
                doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
                links.append(f'<a href="https://doi.org/{esc(doi)}">[doi]</a>')

            bib_raw = e["raw"].strip()
            bib_raw = re.sub(r"\n\s+", "\n  ", bib_raw)
            bib_html = esc(bib_raw)

            pieces: list[str] = []
            if authors:
                pieces.append(f'<div class="pub-authors">{esc(authors)} ({esc(field(e, "year"))})</div>')
            if title:
                pieces.append(f'<div class="pub-title">{esc(title)}</div>')

            meta = []
            if venue:
                meta.append(esc(venue))
            if address:
                meta.append(esc(address))
            if pages:
                meta.append(esc(pages))
            if meta:
                pieces.append(f'<div class="pub-meta">{" · ".join(meta)}</div>')

            link_line = " ".join(links)
            pieces.append(
                '<div class="pub-links">'
                + link_line
                + ' <button class="bib-toggle" type="button">[bib]</button>'
                + '<div class="bib-pop" hidden><pre>'
                + bib_html
                + "</pre></div></div>"
            )

            items_html.append('<div class="pub-item">' + "\n".join(pieces) + "</div>")
        items_html.append("  </div>")
        items_html.append("</details>")
    return "\n".join(items_html)


def inject_pubs(html_text: str, pubs_html: str) -> str:
    if "<!-- PUBS_START -->" in html_text and "<!-- PUBS_END -->" in html_text:
        return re.sub(
            r"(<!-- PUBS_START -->)(.*?)(<!-- PUBS_END -->)",
            r"\1\n" + pubs_html + r"\n\3",
            html_text,
            flags=re.S,
        )
    return re.sub(
        r'(<div class="pubs">).*?(</div>\s*</div>\s*</div>\s*</header>)',
        r"\1\n" + pubs_html + r"\n\2",
        html_text,
        flags=re.S,
    )


def build_all_bib() -> str:
    bib_files = sorted(
        p for p in BIB_DIR.glob("*.bib") if p.name not in {"all.bib", "all.pub"}
    )
    if not bib_files:
        raise SystemExit(f"No .bib files found in {BIB_DIR}")

    entries: list[dict] = []
    for path in bib_files:
        entries.extend(parse_bibtex_entries(path.read_text(encoding="utf-8")))

    def year_key(e: dict) -> int:
        y = e["fields"].get("year", "").strip()
        return int(re.sub(r"\\D", "", y) or 0)

    entries.sort(key=lambda e: (-year_key(e), e["key"]))

    formatted = []
    for e in entries:
        raw = e["raw"].strip()
        formatted.append(raw)
    return "\n\n".join(formatted) + "\n"


def main() -> None:
    if not BIB_DIR.exists():
        raise SystemExit(f"Missing {BIB_DIR}")

    all_bib = build_all_bib()
    ALL_BIB_PATH.write_text(all_bib, encoding="utf-8")
    ALL_BIB_COMPAT.write_text(all_bib, encoding="utf-8")

    entries = parse_bibtex_entries(all_bib)
    pubs_html = build_pubs_html(entries)
    html_text = INDEX_PATH.read_text(encoding="utf-8")
    new_html = inject_pubs(html_text, pubs_html)
    INDEX_PATH.write_text(new_html, encoding="utf-8")
    print("Updated index.html publications from", ALL_BIB_PATH)


if __name__ == "__main__":
    main()

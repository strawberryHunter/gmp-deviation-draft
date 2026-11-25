"""Put entered text into Markdown so it is shown exactly as entered.

The draft restates what the reporter wrote. If that text goes into Markdown
raw, characters a QA author types naturally are *interpreted* instead of
shown: a "|" in a parameter name adds a table column and shifts the actual
result into the wrong column, "#4 포트" turns into a heading, "> ..." into a
quote box, "*재시험 전*" loses its asterisks, "2~8°C ~ 10~15분" can be struck
through on GitHub. In a GxP record that is an altered fact.

So every entered value is backslash-escaped (CommonMark escapes, which GitHub
and devdraft.docx_out both undo). Only characters that can change meaning are
escaped, so ordinary text such as "3.40-3.60" or "SYN-mAb-07" stays readable
in the raw file.
"""
from __future__ import annotations

import re

# Characters that change meaning anywhere in a line.
_INLINE = re.compile(r"([\\`*|\[\]~])")
# "_" only where it could open/close emphasis (not inside SYN_mAb_07).
_UNDERSCORE = re.compile(r"(?<![0-9A-Za-z가-힣])_|_(?![0-9A-Za-z가-힣])")
# "<tag" (raw HTML) and "&name;" (entities) only.
_ANGLE = re.compile(r"<(?=[A-Za-z/!?])")
_AMP = re.compile(r"&(?=#?[0-9A-Za-z]+;)")
# Line starts that make headings, quotes, lists or setext underlines.
_LINE_START = re.compile(r"^(\s*)([#>+=-])")
_ORDERED = re.compile(r"^(\s*\d{1,9})([.)])(?=\s|$)")  # "1. x" is a list, "3.40" is not


def inline(value) -> str:
    """One line of entered text, safe in a paragraph or a table cell."""
    s = "" if value is None else str(value)
    s = _INLINE.sub(r"\\\1", s)
    s = _UNDERSCORE.sub(r"\\_", s)
    s = _ANGLE.sub(r"\\<", s)
    s = _AMP.sub(r"\\&", s)
    s = _LINE_START.sub(r"\1\\\2", s)
    s = _ORDERED.sub(r"\1\\\2", s)
    return s


def block(value) -> str:
    """Multi-line entered text: each line escaped, line breaks kept as hard
    breaks (Markdown would otherwise join the lines into one sentence)."""
    lines = ("" if value is None else str(value)).splitlines() or [""]
    return "  \n".join(inline(line.rstrip()) for line in lines)

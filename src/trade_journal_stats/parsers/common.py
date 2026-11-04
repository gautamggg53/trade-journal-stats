"""Shared helpers: decoding, CSV/HTML table reading, numbers, dates, timezones."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone, tzinfo
from html.parser import HTMLParser
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..models import InputError

_OFFSET_RE = re.compile(r"^(?:utc|gmt)?\s*([+-])(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)


def get_tz(name: str | None) -> tzinfo:
    """Return a tzinfo for an IANA name (``Europe/London``), ``UTC`` or an offset (``+02:00``)."""
    if not name or name.strip().upper() in ("UTC", "GMT", "Z"):
        return timezone.utc
    text = name.strip()
    m = _OFFSET_RE.match(text)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        delta = timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0))
        return timezone(sign * delta)
    try:
        return ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InputError(
            f"unknown timezone {name!r}; use an IANA name such as "
            "'Europe/London' or an offset such as '+02:00'"
        ) from exc


def decode(data: bytes) -> str:
    """Decode bytes, honouring UTF-16/UTF-8 BOMs (MT5 reports are often UTF-16)."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8")
    # UTF-16 without BOM: lots of NUL bytes in the first chunk.
    head = data[:200]
    if head and head.count(b"\x00") > len(head) // 4:
        return data.decode("utf-16-le" if head[1:2] == b"\x00" else "utf-16-be")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def looks_like_html(text: str) -> bool:
    head = text[:4000].lower()
    return "<table" in head or "<html" in head or "<!doctype html" in head


_SEP_DIRECTIVE = re.compile(r'^\s*"?sep=(.)"?\s*$', re.IGNORECASE)
_DELIMITERS = (",", ";", "\t")


def read_csv_rows(text: str) -> list[list[str]]:
    """Read CSV text, sniffing the delimiter among comma, semicolon and tab.

    An Excel ``sep=;`` directive on the first line is honoured and dropped.
    Otherwise the delimiter is the one that appears most often on the first line
    outside double quotes, so commas inside quoted header cells are not counted.
    """
    lines = text.splitlines(keepends=True)
    first = lines[0] if lines else ""
    directive = _SEP_DIRECTIVE.match(first)
    if directive:
        delim = directive.group(1)
        text = "".join(lines[1:])
    else:
        counts = dict.fromkeys(_DELIMITERS, 0)
        quoted = False
        for ch in first:
            if ch == '"':
                quoted = not quoted
            elif not quoted and ch in counts:
                counts[ch] += 1
        delim = max(counts, key=lambda d: counts[d]) if any(counts.values()) else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    return [[c.strip() for c in row] for row in reader if any(c.strip() for c in row)]


class _TableParser(HTMLParser):
    """Flatten every <tr> in a document into a list of cell strings (colspan expanded)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._span = 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            span = dict(attrs).get("colspan") or "1"
            self._span = int(span) if span.isdigit() else 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._row.extend([""] * (self._span - 1))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def read_html_rows(text: str) -> list[list[str]]:
    parser = _TableParser()
    parser.feed(text)
    parser.close()
    return parser.rows


def norm(header: str) -> str:
    """Lower-case and collapse whitespace."""
    return " ".join(header.strip().lower().split())


_NUM_STRIP = re.compile(r"[^\d.,\-+eE]")


def parse_number(
    value: str, *, field: str = "value", decimal_comma: bool = False, empty: float | None = None
) -> float:
    """Parse a number such as ``1 234.50``, ``-1,234.50``, ``(12.30)``, ``$5`` or ``−3``."""
    text = (value or "").strip().replace("\u2212", "-").replace("\u00a0", "").replace(" ", "")
    if text in ("", "-", "—"):
        if empty is not None:
            return empty
        raise InputError(f"missing {field}")
    negative = text.startswith("(") and text.endswith(")")
    text = _NUM_STRIP.sub("", text)
    text = text.replace(".", "").replace(",", ".") if decimal_comma else text.replace(",", "")
    try:
        number = float(text)
    except ValueError as exc:
        raise InputError(f"cannot read {field} {value!r} as a number") from exc
    return -abs(number) if negative else number


_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%d/%m/%Y %H:%M:%S.%f",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%Y-%m-%d",
)


def parse_datetime(
    value: str, tz: tzinfo, *, fmt: str | None = None, field: str = "time"
) -> datetime:
    """Parse a timestamp. Naive values are interpreted in ``tz``.

    Day-first is assumed for ``dd/mm/yyyy``; pass ``fmt`` (a ``strptime`` format)
    for month-first or any other layout.
    """
    text = (value or "").strip()
    if not text:
        raise InputError(f"missing {field}")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed: datetime | None = None
    if fmt:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError as exc:
            raise InputError(f"{field} {value!r} does not match --date-format {fmt!r}") from exc
    else:
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            for f in _DATE_FORMATS:
                try:
                    parsed = datetime.strptime(text, f)
                    break
                except ValueError:
                    continue
    if parsed is None:
        raise InputError(
            f"cannot read {field} {value!r}; pass --date-format, e.g. '%m/%d/%Y %H:%M'"
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed


def parse_side(value: str) -> str:
    v = norm(value)
    if v in ("buy", "long", "b", "l") or v.startswith(("buy", "long")):
        return "long"
    if v in ("sell", "short", "s") or v.startswith(("sell", "short")):
        return "short"
    return ""

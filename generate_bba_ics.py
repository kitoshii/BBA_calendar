# generate_ics.py
import io
import re
import sys
from datetime import date, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from ics import Calendar, Event

TERM_DATES_URL = "https://arkbolingbrokeacademy.org/calendar/term-dates"
OUT_ICS = "calendar.ics"
DEBUG = 1

# Below this, assume the PDF's layout changed and we mostly failed to parse
# it, rather than that the school genuinely only listed a handful of dates.
MIN_EVENTS_PER_PDF = 15

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Sept": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
# Longest names first so e.g. "September" isn't cut short by "Sep" matching first.
MONTH_PATTERN = "|".join(re.escape(m) for m in sorted(MONTHS, key=len, reverse=True))
WEEKDAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
# Weekday name is optional: some future layout may drop it and just say "7th
# September 2026". It's only used to help split label text from the date
# when present.
DATE_TOKEN_RE = re.compile(
    rf"(?:\b(?:{WEEKDAYS})\b,?\s+)?"
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)\b"
    rf"(?:\s+({MONTH_PATTERN})\.?)?"
    rf"(?:\s+(\d{{4}}))?"
)
AT_TIME_RE = re.compile(r"\bat\s+(\d{1,2}[:.]\d{2}\s*[ap]\.?m\.?)\b", re.IGNORECASE)
TRAILING_PAREN_RE = re.compile(r"\(([^)]+)\)\s*$")
SECTION_HEADER_RE = re.compile(r"^[A-Z][A-Z ]+TERM$")
YEAR_HEADER_RE = re.compile(r"Term dates\s+(\d{4})\s*-\s*(\d{4})", re.IGNORECASE)


def find_pdf_links(html):
    """Find every "term dates" PDF linked from the page.

    Matches on the href *or* the link's visible text, since either one
    (the filename convention, or the label) could change independently in
    a future year - as long as one of them still says "term dates" we'll
    still find it.
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []
    all_pdfs = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        text = a.get_text(" ", strip=True)
        all_pdfs.append((href, text))
        if "term" in href.lower() or "term dates" in text.lower():
            links.append(urljoin(TERM_DATES_URL, href))
    if not links and DEBUG and all_pdfs:
        print("No PDF looked like term dates. All PDF links found on the page:", file=sys.stderr)
        for href, text in all_pdfs:
            print(f"  {href!r} labelled {text!r}", file=sys.stderr)
    return links


def extract_pdf_text(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def academic_year_window(text):
    """A generous (start, end) date window derived from the PDF's own
    "Term dates YYYY-YYYY" heading, used to sanity-check parsed events
    actually belong to the year the document claims to cover."""
    m = YEAR_HEADER_RE.search(text)
    if not m:
        return None
    y1, y2 = int(m.group(1)), int(m.group(2))
    return date(y1, 8, 1), date(y2, 9, 30)


def parse_date_tokens(segment):
    # Ranges often omit the month/year on the first date, e.g.
    # "Monday 15th - Friday 19th February 2027" -> inherit from the last token.
    tokens = []
    for m in DATE_TOKEN_RE.finditer(segment):
        day, month, year = m.groups()
        tokens.append([int(day), month, int(year) if year else None])
    for i in range(len(tokens) - 2, -1, -1):
        if tokens[i][1] is None:
            tokens[i][1] = tokens[i + 1][1]
        if tokens[i][2] is None:
            tokens[i][2] = tokens[i + 1][2]
    return tokens


def parse_term_dates_text(text):
    """Parse a Bolingbroke Academy term-dates PDF's extracted text into
    (title, start_date, end_date_inclusive) tuples.

    Returns (events, warnings): warnings is a list of lines that looked
    like they should contain a date but couldn't be parsed, so the caller
    can fail loudly instead of silently publishing an incomplete calendar.
    """
    events = []
    warnings = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if SECTION_HEADER_RE.match(line):
            continue
        if line.startswith("Bolingbroke Academy") or line.startswith("Information for"):
            continue
        if "tbc" in line.lower():
            # Provisional lines (A Level / GCSE results days) - not real dates yet.
            if DEBUG:
                print(f"Skipping provisional line: {line!r}")
            continue

        first_token = DATE_TOKEN_RE.search(line)
        if not first_token:
            # Continuation line, e.g. "Years 7 and 12 only" qualifying the
            # event on the line above.
            if events:
                title, s, e = events[-1]
                events[-1] = (f"{title} ({line})", s, e)
            elif DEBUG:
                print(f"Ignoring unrecognized line: {line!r}")
            continue

        label = line[:first_token.start()].strip()
        date_expr = line[first_token.start():]

        notes = []
        at_match = AT_TIME_RE.search(date_expr)
        if at_match:
            notes.append(f"dismissal at {at_match.group(1)}")
            date_expr = date_expr[:at_match.start()]
        paren_match = TRAILING_PAREN_RE.search(date_expr)
        if paren_match:
            notes.append(paren_match.group(1))
            date_expr = date_expr[:paren_match.start()]

        tokens = parse_date_tokens(date_expr)
        if not tokens:
            warnings.append(line)
            print(f"WARNING: could not parse date for line: {line!r}", file=sys.stderr)
            continue

        try:
            start = date(tokens[0][2], MONTHS[tokens[0][1]], tokens[0][0])
            end = date(tokens[-1][2], MONTHS[tokens[-1][1]], tokens[-1][0])
        except (KeyError, TypeError, ValueError) as exc:
            warnings.append(line)
            print(f"WARNING: bad date tokens for line: {line!r} ({exc})", file=sys.stderr)
            continue

        title = f"{label} ({'; '.join(notes)})" if notes else label
        events.append((title, start, end))
    return events, warnings


def build_calendar(events):
    cal = Calendar()
    seen = set()
    for title, start, end in events:
        key = f"{title}|{start}|{end}"
        if key in seen:
            continue
        seen.add(key)

        e = Event()
        e.name = title
        e.begin = start
        e.make_all_day()
        # DTEND is exclusive: one day after the last inclusive day.
        e.end = end + timedelta(days=1)
        assert e.all_day, f"{title} failed to become an all-day event"
        cal.events.add(e)
    return cal


def parse_pdf(pdf_bytes, source):
    """Parse one term-dates PDF and sanity-check the result, raising if
    anything looks like the document's layout has changed rather than
    silently publishing a broken or empty calendar."""
    text = extract_pdf_text(pdf_bytes)
    events, warnings = parse_term_dates_text(text)

    if warnings:
        raise RuntimeError(
            f"{source}: {len(warnings)} line(s) looked like they should contain a "
            f"date but couldn't be parsed - the PDF layout may have changed:\n"
            + "\n".join(warnings)
        )
    if len(events) < MIN_EVENTS_PER_PDF:
        raise RuntimeError(
            f"{source}: only parsed {len(events)} events (expected at least "
            f"{MIN_EVENTS_PER_PDF}) - the PDF layout may have changed"
        )

    window = academic_year_window(text)
    if window:
        lo, hi = window
        out_of_range = [(t, s, e) for t, s, e in events if not (lo <= s <= hi and lo <= e <= hi)]
        if out_of_range:
            raise RuntimeError(
                f"{source}: {len(out_of_range)} event(s) fall outside the expected "
                f"{lo}..{hi} window - date parsing is likely broken: {out_of_range}"
            )
    elif DEBUG:
        print(f"{source}: couldn't find a 'Term dates YYYY-YYYY' heading to sanity-check against")

    return events


def main():
    r = requests.get(TERM_DATES_URL, timeout=20)
    r.raise_for_status()
    pdf_urls = find_pdf_links(r.text)
    if not pdf_urls:
        raise RuntimeError("No term-dates PDF links found on the page")

    all_events = []
    for url in pdf_urls:
        if DEBUG:
            print(f"Fetching {url}")
        pr = requests.get(url, timeout=20)
        pr.raise_for_status()
        events = parse_pdf(pr.content, url)
        if DEBUG:
            print(f"  -> {len(events)} events")
        all_events.extend(events)

    cal = build_calendar(all_events)
    with open(OUT_ICS, "w", encoding="utf-8") as f:
        f.writelines(cal)
    print(f"Wrote {OUT_ICS} ({len(cal.events)} events)")


if __name__ == "__main__":
    main()

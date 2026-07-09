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

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}
WEEKDAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
WEEKDAY_RE = re.compile(rf"\b(?:{WEEKDAYS})\b")
DATE_TOKEN_RE = re.compile(
    rf"\b(?:{WEEKDAYS})\s+(\d{{1,2}})(?:st|nd|rd|th)"
    rf"(?:\s+({'|'.join(MONTHS)}))?"
    rf"(?:\s+(\d{{4}}))?"
)
AT_TIME_RE = re.compile(r"\bat\s+(\d{1,2}:\d{2}\s*[ap]m)\b", re.IGNORECASE)
TRAILING_PAREN_RE = re.compile(r"\(([^)]+)\)\s*$")
SECTION_HEADER_RE = re.compile(r"^[A-Z][A-Z ]+TERM$")


def find_pdf_links(html):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf") and "term" in href.lower():
            links.append(urljoin(TERM_DATES_URL, href))
    return links


def extract_pdf_text(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


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
    (title, start_date, end_date_inclusive) tuples."""
    events = []
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

        first_wd = WEEKDAY_RE.search(line)
        if not first_wd:
            # Continuation line, e.g. "Years 7 and 12 only" qualifying the
            # event on the line above.
            if events:
                title, s, e = events[-1]
                events[-1] = (f"{title} ({line})", s, e)
            elif DEBUG:
                print(f"Ignoring unrecognized line: {line!r}")
            continue

        label = line[:first_wd.start()].strip()
        date_expr = line[first_wd.start():]

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
            print(f"WARNING: could not parse date for line: {line!r}", file=sys.stderr)
            continue

        try:
            start = date(tokens[0][2], MONTHS[tokens[0][1]], tokens[0][0])
            end = date(tokens[-1][2], MONTHS[tokens[-1][1]], tokens[-1][0])
        except (KeyError, TypeError, ValueError) as exc:
            print(f"WARNING: bad date tokens for line: {line!r} ({exc})", file=sys.stderr)
            continue

        title = f"{label} ({'; '.join(notes)})" if notes else label
        events.append((title, start, end))
    return events


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
        events = parse_term_dates_text(extract_pdf_text(pr.content))
        if DEBUG:
            print(f"  -> {len(events)} events")
        all_events.extend(events)

    cal = build_calendar(all_events)
    with open(OUT_ICS, "w", encoding="utf-8") as f:
        f.writelines(cal)
    print(f"Wrote {OUT_ICS} ({len(cal.events)} events)")


if __name__ == "__main__":
    main()

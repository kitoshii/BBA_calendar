"""Regression test for the term-dates PDF parser.

Runs the parser against two real, previously-verified PDFs and checks the
output matches exactly. If the school changes the PDF's wording/layout,
this should fail loudly instead of the calendar silently going stale or
producing garbage dates.
"""
from datetime import date

from generate_bba_ics import (
    academic_year_window,
    build_calendar,
    extract_pdf_text,
    find_pdf_links,
    parse_pdf,
    parse_term_dates_text,
)

EXPECTED_2025_26 = [
    ('Autumn term 1 starts (Years 7 and 12 only)', '2025-09-03', '2025-09-03'),
    ('Autumn term 1 starts (All year groups)', '2025-09-04', '2025-09-04'),
    ('Speech Day (half day)', '2025-09-17', '2025-09-17'),
    ('Network Inset Day', '2025-09-19', '2025-09-19'),
    ('Network Inset Day', '2025-10-17', '2025-10-17'),
    ('Autumn term 1 ends', '2025-10-24', '2025-10-24'),
    ('Half term holidays', '2025-10-27', '2025-10-31'),
    ('Autumn term 2 starts', '2025-11-03', '2025-11-03'),
    ('Academy Inset Day', '2025-11-17', '2025-11-17'),
    ('Occasional Day (school closed)', '2025-12-01', '2025-12-01'),
    ('Autumn term 2 ends (dismissal at 12:35pm)', '2025-12-18', '2025-12-18'),
    ('Christmas holidays', '2025-12-19', '2026-01-02'),
    ('Spring term 1 starts', '2026-01-05', '2026-01-05'),
    ('Spring term 1 ends', '2026-02-12', '2026-02-12'),
    ('Network Inset Day', '2026-02-13', '2026-02-13'),
    ('Half term holidays', '2026-02-16', '2026-02-20'),
    ('Spring term 2 starts', '2026-02-23', '2026-02-23'),
    ('Academy Inset Day', '2026-03-02', '2026-03-02'),
    ('Spring term 2 ends (dismissal at 12:35pm)', '2026-03-27', '2026-03-27'),
    ('Easter holidays', '2026-03-30', '2026-04-10'),
    ('Academy Inset Day', '2026-04-13', '2026-04-13'),
    ('Summer term 1 starts', '2026-04-14', '2026-04-14'),
    ('May Bank Holiday (school closed)', '2026-05-04', '2026-05-04'),
    ('Summer term 1 ends', '2026-05-22', '2026-05-22'),
    ('Half term holidays', '2026-05-25', '2026-05-29'),
    ('Summer term 2 starts', '2026-06-01', '2026-06-01'),
    ('Digital Day (all pupils learning at home)', '2026-07-02', '2026-07-02'),
    ('Network Inset Day', '2026-07-03', '2026-07-03'),
    ('Summer term 2 ends (dismissal at 12:35pm)', '2026-07-16', '2026-07-16'),
]

EXPECTED_2026_27 = [
    ('Autumn term 1 starts (Years 7 and 12 only)', '2026-09-07', '2026-09-07'),
    ('Autumn term 1 starts (All year groups)', '2026-09-08', '2026-09-08'),
    ('Speech Day (half day)', '2026-09-16', '2026-09-16'),
    ('Network Inset Day', '2026-09-18', '2026-09-18'),
    ('Network Inset Day', '2026-10-16', '2026-10-16'),
    ('Autumn term 1 ends', '2026-10-23', '2026-10-23'),
    ('Half term holidays', '2026-10-26', '2026-10-30'),
    ('Autumn term 2 starts', '2026-11-02', '2026-11-02'),
    ('Academy Inset Day', '2026-11-16', '2026-11-16'),
    ('Occasional Day (school closed)', '2026-12-07', '2026-12-07'),
    ('Autumn term 2 ends (dismissal at 12:35pm)', '2026-12-18', '2026-12-18'),
    ('Christmas holidays', '2026-12-21', '2027-01-01'),
    ('Spring term 1 starts', '2027-01-04', '2027-01-04'),
    ('Spring term 1 ends', '2027-02-11', '2027-02-11'),
    ('Network Inset Day', '2027-02-12', '2027-02-12'),
    ('Half term holidays', '2027-02-15', '2027-02-19'),
    ('Spring term 2 starts', '2027-02-22', '2027-02-22'),
    ('Academy Inset Day', '2027-03-01', '2027-03-01'),
    ('Spring term 2 ends (dismissal at 12:35pm)', '2027-03-25', '2027-03-25'),
    ('Easter holidays', '2027-03-26', '2027-04-09'),
    ('Academy Inset Day', '2027-04-12', '2027-04-12'),
    ('Summer term 1 starts', '2027-04-13', '2027-04-13'),
    ('May Bank Holiday (school closed)', '2027-05-03', '2027-05-03'),
    ('Summer term 1 ends', '2027-05-28', '2027-05-28'),
    ('Half term holidays', '2027-05-31', '2027-06-04'),
    ('Summer term 2 starts', '2027-06-07', '2027-06-07'),
    ('Digital Day (all pupils learning at home)', '2027-07-01', '2027-07-01'),
    ('Network Inset Day', '2027-07-02', '2027-07-02'),
    ('Summer term 2 ends (dismissal at 12:35pm)', '2027-07-20', '2027-07-20'),
]


def parse_fixture(path):
    with open(path, "rb") as f:
        text = extract_pdf_text(f.read())
    events, warnings = parse_term_dates_text(text)
    assert not warnings, f"{path}: unexpected parse warnings: {warnings}"
    return [(title, s.isoformat(), e.isoformat()) for title, s, e in events]


def check(path, expected):
    actual = parse_fixture(path)
    assert actual == expected, (
        f"{path}: parsed events don't match expected.\n"
        f"Expected {len(expected)} events, got {len(actual)}.\n"
        f"Expected: {expected}\nActual:   {actual}"
    )
    print(f"OK: {path} ({len(actual)} events match)")

    # parse_pdf() wraps the same parsing with sanity checks - it should
    # accept these known-good real documents without raising.
    with open(path, "rb") as f:
        events = parse_pdf(f.read(), path)
    assert len(events) == len(expected)
    print(f"OK: {path} passes parse_pdf() sanity checks")


def check_all_day_output():
    events = [("Test Day", date(2026, 1, 1), date(2026, 1, 1))]
    cal = build_calendar(events)
    (event,) = cal.events
    assert event.all_day, "build_calendar produced a non-all-day event"
    print("OK: build_calendar produces all-day events")


def check_unparseable_line_warns():
    # Has a day-ordinal token but no month/year to inherit from anywhere.
    events, warnings = parse_term_dates_text("Some Event   Monday 15th\n")
    assert warnings, "expected a warning for a date-like line missing month/year"
    print("OK: unparseable lines are reported as warnings")


def check_academic_year_window():
    window = academic_year_window("Bolingbroke Academy: Term dates 2027-2028\n")
    assert window == (date(2027, 8, 1), date(2028, 9, 30)), window
    assert academic_year_window("no heading here") is None
    print("OK: academic_year_window extracts the year range from the PDF heading")


def check_find_pdf_links_matches_href_or_text():
    html = """
    <a href="/files/2028-05/dates.pdf">Term Dates 2028-29 (12 KB)</a>
    <a href="/files/2029-05/BOL%20Term%20Dates%202029-30.pdf">Download (15 KB)</a>
    <a href="/files/other.pdf">Unrelated document</a>
    """
    links = find_pdf_links(html)
    assert len(links) == 2, links
    assert any("dates.pdf" in l for l in links)
    assert any("Term%20Dates%202029-30" in l for l in links)
    print("OK: find_pdf_links matches on href OR link text")


if __name__ == "__main__":
    check("tests/fixtures/term-dates-2025-26.pdf", EXPECTED_2025_26)
    check("tests/fixtures/term-dates-2026-27.pdf", EXPECTED_2026_27)
    check_all_day_output()
    check_unparseable_line_warns()
    check_academic_year_window()
    check_find_pdf_links_matches_href_or_text()
    print("All tests passed.")

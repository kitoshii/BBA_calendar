# generate_ics.py
import os
import sys
import traceback
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote_plus
from ics import Calendar, Event


URL = "https://arkbolingbrokeacademy.org/calendar"
OUT_ICS = "calendar.ics"
TIMEZONE = "UTC"  # page used UTC template links; adjust if needed
DEBUG=1

def parse_google_template_href(href):
    # Example href contains:
    # ...calendar/render?action=TEMPLATE&ctz=UTC&dates=20251017T000000%2F20251017T000000&text=Network+INSET+day...
    q = parse_qs(urlparse(href).query)
    dates = q.get("dates", [""])[0]
    text = q.get("text", [""])[0]
    # decode pluses/percent encoding
    text = unquote_plus(text)
    return dates, text

def parse_dates_field(dates_str):
    # dates_str examples:
    # 1) 20251017T000000/20251017T000000
    # 2) 20251027/20251031  (maybe)
    if "/" not in dates_str:
        return None, None
    start_s, end_s = dates_str.split("/", 1)

    def to_dt(s):
        # YYYYMMDDTHHMMSS or YYYYMMDD
        if "T" in s:
            return datetime.strptime(s, "%Y%m%dT%H%M%S")
        else:
            return datetime.strptime(s, "%Y%m%d")
    start = to_dt(start_s)
    end = to_dt(end_s)
    return start, end

def main():
    r = requests.get(URL, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    cal = Calendar()
    seen = set()

    for a in soup.find_all("a", href=True):
        if "calendar.google.com/calendar/render" in a["href"] and "action=TEMPLATE" in a["href"]:
            dates_str, title = parse_google_template_href(a["href"])
            if not dates_str or not title:
                continue
            start, end = parse_dates_field(dates_str)
            key = f"{title}|{dates_str}"
            if key in seen:
                continue
            seen.add(key)

            e = Event()
            e.name = title

            # Every event on this site's calendar page is a whole-day concept
            # (INSET days, term dates, holidays) — the Google Calendar links
            # always encode them as midnight-to-midnight timestamps, never a
            # genuine time of day. Treat them as all-day based on the date
            # portion alone so stray time components can't turn them into a
            # 24h-long *timed* event (which some calendar apps then render
            # shifted by the viewer's UTC offset, e.g. "1am to 1am").
            if start and end:
                if DEBUG:
                    print(f"Event: {title} | {start} to {end}")
                start_date = start.date()
                end_date = end.date()
                e.begin = start_date
                e.make_all_day()
                # DTEND is exclusive: one day after the last inclusive day.
                # Set it explicitly even for single-day events so DTEND is
                # always present in the output.
                last_day = end_date if end_date > start_date else start_date
                e.end = last_day + timedelta(days=1)
                assert e.all_day, f"{title} failed to become an all-day event"
            else:
                e.begin = start
                e.end = end

            cal.events.add(e)

    with open(OUT_ICS, "w", encoding="utf-8") as f:
        f.writelines(cal)
    print(f"Wrote {OUT_ICS} ({len(cal.events)} events)")

if __name__ == "__main__":
    main()

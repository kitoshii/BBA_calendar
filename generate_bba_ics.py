# generate_ics.py
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote_plus
from ics import Calendar, Event
from datetime import datetime
import os

URL = "https://arkbolingbrokeacademy.org/calendar"
OUT_ICS = "calendar.ics"
TIMEZONE = "UTC"  # page used UTC template links; adjust if needed

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
            # If the start and end are the same midnight times, treat as all-day for that date
            # many school events are whole-day; ics lib accepts datetimes too
            e.begin = start
            # for all-day events Google sometimes uses same start/end midnight:
            # make end one day after for all-day semantics if times are midnight and equal
            if start and end and start == end and start.time().hour == 0 and start.time().minute == 0:
                e.end = end  # leave as-is; consumer may treat as zero-length; you may add +1 day if desired
            else:
                e.end = end
            cal.events.add(e)

    with open(OUT_ICS, "w", encoding="utf-8") as f:
        f.writelines(cal)
    print(f"Wrote {OUT_ICS} ({len(cal.events)} events)")

if __name__ == "__main__":
    main()

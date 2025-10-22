# --- add these imports at top if not already present ---
import json
import re
from bs4 import BeautifulSoup

# --- add helpers ---

_US_TERMS = [
    "united states", "u.s.", "u.s.a.", "usa", "us only", "remote - us", "remote (us)",
    "authorized to work in the us", "work authorization in the us", "us citizenship"
]

# State names/abbrevs for extra signal (keep short to avoid false positives)
_US_STATE_NAMES = [
    "alabama","alaska","arizona","arkansas","california","colorado","connecticut","delaware",
    "florida","georgia","hawaii","idaho","illinois","indiana","iowa","kansas","kentucky",
    "louisiana","maine","maryland","massachusetts","michigan","minnesota","mississippi","missouri",
    "montana","nebraska","nevada","new hampshire","new jersey","new mexico","new york",
    "north carolina","north dakota","ohio","oklahoma","oregon","pennsylvania","rhode island",
    "south carolina","south dakota","tennessee","texas","utah","vermont","virginia","washington",
    "west virginia","wisconsin","wyoming", "district of columbia", "washington, dc", "dc"
]
_US_STATE_ABBR = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY",
    "LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND",
    "OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC"
]

# Avoid false positives like "react quickly", "reaction", "reactive"
_REACT_RE = re.compile(r"\breact(?:\.?js|\s*js)?\b", re.I)
_BAD_REACT_CONTEXT = re.compile(r"\breact(ive|ion|s|or|ants?)\b", re.I)

_CITY_STATE_RE = re.compile(r"\b[A-Z][a-zA-Z]+,\s?(?:{})\b".format("|".join(_US_STATE_ABBR)))

def _is_us_text(txt: str) -> bool:
    t = txt.lower()
    if any(term in t for term in _US_TERMS):
        return True
    if any(name in t for name in _US_STATE_NAMES):
        return True
    # “City, ST” pattern e.g., “Denver, CO”
    if _CITY_STATE_RE.search(txt):
        return True
    return False

def _contains_react(txt: str) -> bool:
    if _BAD_REACT_CONTEXT.search(txt):
        return False
    return bool(_REACT_RE.search(txt))

def _extract_jsonld_jobposting(soup: BeautifulSoup):
    """Return a list of normalized dicts from schema.org JobPosting if present."""
    jobs = []
    for s in soup.find_all("script", type=lambda v: v and "ld+json" in v):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue

        # Some pages embed arrays or graphs
        candidates = data if isinstance(data, list) else [data]
        for node in candidates:
            if not isinstance(node, dict):
                continue
            # Flatten @graph if present
            graph = node.get("@graph")
            if isinstance(graph, list):
                for g in graph:
                    if isinstance(g, dict):
                        candidates.append(g)

            t = (node.get("@type") or node.get("type") or "")
            if isinstance(t, list):
                is_job = any(x.lower() == "jobposting" for x in t if isinstance(x, str))
            else:
                is_job = str(t).lower() == "jobposting"

            if not is_job:
                continue

            title = (node.get("title") or node.get("name") or "")
            desc  = node.get("description") or ""

            # Locations can be under jobLocation / applicantLocationRequirements
            locations = []
            jl = node.get("jobLocation")
            if isinstance(jl, list):
                for loc in jl:
                    addr = (loc or {}).get("address") or {}
                    locations.append(" ".join(filter(None, [
                        addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")
                    ])))
            elif isinstance(jl, dict):
                addr = jl.get("address") or {}
                locations.append(" ".join(filter(None, [
                    addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")
                ])))

            # applicantLocationRequirements may specify “US”
            alr = node.get("applicantLocationRequirements")
            if isinstance(alr, list):
                for req in alr:
                    locations.append(str(req))
            elif alr:
                locations.append(str(alr))

            jobs.append({
                "title": title or "",
                "description": desc or "",
                "locations_text": " | ".join([l for l in locations if l]) or ""
            })
    return jobs

def _classify_react_us_from_html(base_url: str, html: str):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)

    # 1) JSON-LD JobPosting first (most structured)
    for job in _extract_jsonld_jobposting(soup):
        has_react = _contains_react(job["title"]) or _contains_react(job["description"])
        is_us = _is_us_text(job["locations_text"]) or _is_us_text(job["description"])
        if has_react and is_us:
            return True, "React job in the US found via JSON-LD JobPosting."
        if has_react:
            return False, "React job found via JSON-LD, but US location not clear."

    # 2) Fall back to page text heuristics
    has_react = _contains_react(text)
    is_us = _is_us_text(text)

    if has_react and is_us:
        return True, "React job in the US found via page text."
    if has_react:
        return False, "React job found, but US location not clear."
    return False, "No React job signals found."
# --- add the new public checker ---

def check_react_job_us(url: str):
    """Return (bool|None, message) like your existing check_client_portal:
       True  => React + US confirmed
       False => not React/US (or ambiguous)
       None  => network/error
    """
    try:
        r = _fetch(url)
        ok, msg = _classify_react_us_from_html(r.url, r.text)
        if ok:
            return True, msg

        # Optional: follow one “Jobs/Careers” style link and try again (lightweight crawl)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            label = (a.get_text() or "").strip().lower()
            if any(k in label for k in ["careers", "jobs", "open roles", "join us"]):
                probe = urljoin(r.url, a["href"])
                try:
                    r2 = _fetch(probe)
                    ok2, msg2 = _classify_react_us_from_html(r2.url, r2.text)
                    if ok2:
                        return True, f"Found via careers page {probe}: {msg2}"
                    # if React found but not US, keep that message as a fallback
                    if "React job found" in msg2:
                        return False, f"Found via careers page {probe}: {msg2}"
                except requests.RequestException:
                    pass

        return False, msg
    except requests.RequestException as e:
        return None, f"Request failed: {e}"

# churchScrape.py
import re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})

# Text that often appears ON the site (menu labels, headings, buttons)
TEXT_KEYWORDS = [
    # core
    "client login", "log in", "login", "sign in", "signin",
    "client portal", "portal", "client center", "client access",
    "my account", "account login", "secure login", "secure portal",
    # tasks commonly routed through portals
    "file upload", "upload files", "upload documents",
    "share files", "send files", "pay invoice", "make a payment",
    "payment portal", "bill pay", "tax organizer", "organizer",
]

# Hints in hrefs (vendors + common paths). These catch off-site portals.
HREF_HINTS = [
    # vendor domains
    "sharefile.com",          # Citrix ShareFile
    "smartvault.com",         # SmartVault
    "netclientcs.com",        # Thomson Reuters NetClient CS
    "clientaxcess.com",       # CCH Axcess
    "onvio.us",               # Thomson Reuters Onvio
    "canopytax.com",          # Canopy
    "securefilepro.com",      # Drake Portals
    "liscio.me", "app.liscio",
    "taxcaddy.com",           # SurePrep TaxCaddy
    "verifyle.com",
    "fileinvite.com",
    "suralink.com",
    "intuit.com/link",        # Intuit Link
    # generic paths/words
    "client-portal", "clientportal", "client_center", "clientcenter",
    "/portal", "/login", "/signin", "/clients", "/account"
]

# Common “guess” paths to probe if the home page doesn’t show it
COMMON_PORTAL_PATHS = [
    "/client-portal", "/clientportal", "/client-login",
    "/clientcenter", "/portal", "/login", "/clients"
]

def _fetch(url):
    r = SESSION.get(url, timeout=15, allow_redirects=True)
    r.raise_for_status()
    return r

def _find_in_html(base_url, html):
    soup = BeautifulSoup(html, "html.parser")

    # 1) Page text
    page_text = soup.get_text(separator=" ", strip=True).lower()
    for kw in TEXT_KEYWORDS:
        if kw in page_text:
            return True, f'Found text match "{kw}" on {base_url}'

    # 2) Anchors & buttons (text + href)
    def norm(s): 
        return " ".join((s or "").strip().lower().split())

    for tag in soup.find_all(["a", "button"], href=True) + soup.find_all("a", href=True):
        text = norm(tag.get_text())
        href = tag.get("href") or ""
        href_l = href.lower()
        abs_href = urljoin(base_url, href)

        if any(kw in text for kw in TEXT_KEYWORDS):
            return True, f'Found link/button "{text}" → {abs_href}'
        if any(h in href_l for h in HREF_HINTS):
            return True, f"Found portal/vendor href → {abs_href}"

    # 3) Non-anchor buttons/spans with onclick or role=link
    for tag in soup.find_all(["button", "span", "div"]):
        label = norm(tag.get_text())
        if any(kw in label for kw in TEXT_KEYWORDS):
            return True, f'Found clickable label "{label}" on {base_url}'

    return False, "No portal signals in initial HTML."

def check_client_portal(url: str):
    try:
        resp = _fetch(url)
        ok, msg = _find_in_html(resp.url, resp.text)
        if ok:
            return True, msg

        # Probe common portal paths
        for path in COMMON_PORTAL_PATHS:
            try:
                probe = urljoin(resp.url.rstrip("/") + "/", path.lstrip("/"))
                r2 = _fetch(probe)
                ok2, msg2 = _find_in_html(r2.url, r2.text)
                if ok2:
                    return True, f"Found via probe {probe}: {msg2}"
            except requests.RequestException:
                pass

        return False, "No client-portal/login signals found."
    except requests.RequestException as e:
        return None, f"Request failed: {e}"

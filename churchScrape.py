# churchScrape.py
import re
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})

# Text that often appears ON the site (menu labels, headings, buttons)
# Split into strong portal phrases (safe to match in plain text) vs generic login words (only trust when linked)
STRONG_TEXT_KEYWORDS = [
    "client login", "client portal", "client center", "client access",
    "my account", "account login", "secure login", "secure portal",
    "file upload", "upload files", "upload documents",
    "share files", "send files",
]
GENERIC_LOGIN_WORDS = [
    "log in", "login", "sign in", "signin"
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

# WordPress login patterns (ignore these)
WP_LOGIN_PATH_RE = re.compile(r"(/wp-login\.php(\?|$))|(/wp-admin/?(\?|$))", re.I)

def _is_wp_login_url(url: str) -> bool:
    try:
        p = urlparse(url or "")
        return bool(WP_LOGIN_PATH_RE.search(p.path or ""))
    except Exception:
        return False

def _has_wp_login(soup: BeautifulSoup, base_url: str) -> bool:
    # a) anchors that go to wp-login/wp-admin
    for a in soup.find_all("a", href=True):
        if _is_wp_login_url(urljoin(base_url, a.get("href"))):
            return True
    # b) forms posting to wp-login
    for f in soup.find_all("form", action=True):
        if _is_wp_login_url(urljoin(base_url, f.get("action"))):
            return True
    return False

def _fetch(url):
    r = SESSION.get(url, timeout=15, allow_redirects=True)
    r.raise_for_status()
    return r

def _find_in_html(base_url, html):
    soup = BeautifulSoup(html, "html.parser")
    wp_present = _has_wp_login(soup, base_url)  # used to filter false positives

    # 1) Page text: match only STRONG portal phrases in free text
    page_text = soup.get_text(separator=" ", strip=True).lower()
    for kw in STRONG_TEXT_KEYWORDS:
        if kw in page_text:
            # If this page ONLY exposes a WP login, don't count it
            if wp_present and "portal" not in kw and "client" not in kw and "account" not in kw and "upload" not in kw and "share" not in kw and "send" not in kw:
                # Overly defensive, but keeps us from tripping on generic text when WP is present
                pass
            else:
                return True, f'Found text match "{kw}" on {base_url}'

    # 2) Anchors & buttons (text + href)
    def norm(s):
        return " ".join((s or "").strip().lower().split())

    # Include both <a> and <button> with hrefs
    link_like_tags = list(soup.find_all(["a", "button"], href=True)) + list(soup.find_all("a", href=True))
    for tag in link_like_tags:
        text = norm(tag.get_text())
        href = tag.get("href") or ""
        abs_href = urljoin(base_url, href)
        href_l = abs_href.lower()

        # If this is a WP login link, ignore it entirely
        if _is_wp_login_url(abs_href):
            continue

        # Text cues: allow both strong and generic login words—but only when it's actually a link
        if any(kw in text for kw in STRONG_TEXT_KEYWORDS) or any(w in text for w in GENERIC_LOGIN_WORDS):
            return True, f'Found link/button "{text}" → {abs_href}'

        # Vendor/path cues in href
        if any(h in href_l for h in HREF_HINTS):
            return True, f"Found portal/vendor href → {abs_href}"

    # 3) Non-anchor buttons/spans/divs with a portal-ish label (no href)
    # Don’t count generic “login” text here—too noisy; require stronger terms
    for tag in soup.find_all(["button", "span", "div"]):
        label = norm(tag.get_text())
        if any(kw in label for kw in STRONG_TEXT_KEYWORDS):
            # If it's clearly a WP-only login page, ignore
            if _has_wp_login(soup, base_url):
                continue
            return True, f'Found clickable label "{label}" on {base_url}'

    return False, "No portal signals in initial HTML."

def check_client_portal(url: str):
    try:
        resp = _fetch(url)
        ok, msg = _find_in_html(resp.url, resp.text)
        if ok:
            return True, msg

        # Probe common portal paths (and still ignore WordPress)
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

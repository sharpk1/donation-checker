# churchScrape.py
import re
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})

# Strong phrases we accept from free text
STRONG_TEXT_KEYWORDS = [
    "client login", "client portal", "client center", "client access",
    "my account", "account login", "secure login", "secure portal",
    "file upload", "upload files", "upload documents",
    "share files", "send files",
]
# Only trusted when it's an actual link and the URL is vendor or client/portal path
GENERIC_LOGIN_WORDS = ["log in", "login", "sign in", "signin"]

# Vendor domains (off-site portals)
VENDOR_DOMAINS = [
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
    "intuit.com",             # Intuit Link lives under this; we’ll check path
]

# Client/portal-ish path hints (safe on same-origin)
CLIENT_PATH_HINTS = [
    "client-portal", "clientportal", "client_center", "clientcenter",
    "/client", "/clients", "/portal", "/client-login", "/clientlogin",
    "/account/login", "/accounts/login"  # still require client/portal word
]

# We explicitly DO NOT treat these generic auth paths as signals by themselves.
GENERIC_AUTH_PATHS = ["/login", "/signin", "/sign-in", "/account", "/user/login", "/auth/login"]

# Common “guess” paths to probe
COMMON_PORTAL_PATHS = [
    "/client-portal", "/clientportal", "/client-login",
    "/clientcenter", "/portal", "/clients"
]

# WordPress login patterns (block these completely)
WP_LOGIN_URL_RE = re.compile(
    r"(^|/)(wp-login\.php|wp-admin|wp-json)(/|$)", re.I
)
WP_ANY_WP_RE = re.compile(r"(^|/)wp-[a-z0-9_-]+", re.I)  # extra safety (e.g., /wp-sso/, /wp-security-login/)

def _is_wp_login_url(url: str) -> bool:
    try:
        p = urlparse(url or "")
        full = (p.path or "") + ("?" + (p.query or "") if p.query else "")
        return bool(WP_LOGIN_URL_RE.search(full) or WP_ANY_WP_RE.search(full))
    except Exception:
        return False

def _fetch(url):
    r = SESSION.get(url, timeout=15, allow_redirects=True)
    r.raise_for_status()
    return r

def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())

def _is_vendor_url(abs_href: str) -> bool:
    try:
        p = urlparse(abs_href)
        host = (p.netloc or "").lower()
        path = (p.path or "").lower()
        if any(v in host for v in VENDOR_DOMAINS):
            # Special case for Intuit: require /link in path
            if "intuit.com" in host:
                return "/link" in path
            return True
        return False
    except Exception:
        return False

def _is_clientish_path(abs_href: str, site_host: str) -> bool:
    try:
        p = urlparse(abs_href)
        host = (p.netloc or "").lower()
        path = (p.path or "").lower()
        # Only treat as client-ish if same-origin OR clear client/portal term in path
        same_origin = site_host and host.endswith(site_host)
        if any(h in path for h in CLIENT_PATH_HINTS):
            # Still ignore if it's clearly WordPress
            if _is_wp_login_url(abs_href):
                return False
            return True if same_origin or any(w in path for w in ["client", "portal"]) else False
        return False
    except Exception:
        return False

def _page_has_wp_login(soup: BeautifulSoup, base_url: str) -> bool:
    # a) anchors/forms that go to wp login/admin/json
    for tag in soup.find_all(["a", "form"], href=True) + soup.find_all("form", action=True):
        href = tag.get("href") or tag.get("action") or ""
        abs_href = urljoin(base_url, href)
        if _is_wp_login_url(abs_href):
            return True
    return False

def _gather_links(soup: BeautifulSoup, base_url: str):
    links = []
    for tag in soup.find_all(["a", "button"], href=True) + soup.find_all("a", href=True):
        text = _norm(tag.get_text())
        href = tag.get("href") or ""
        abs_href = urljoin(base_url, href)
        links.append((text, abs_href))
    return links

def _find_in_html(base_url, html):
    soup = BeautifulSoup(html, "html.parser")
    site_host = urlparse(base_url).netloc.lower()
    wp_present = _page_has_wp_login(soup, base_url)

    # Collect links once for multiple passes
    links = _gather_links(soup, base_url)

    # QUICK VENDOR PASS (highest confidence)
    for text, abs_href in links:
        if _is_wp_login_url(abs_href):
            continue
        if _is_vendor_url(abs_href):
            return True, f"Found vendor portal → {abs_href}"

    # If WordPress login is present AND there are no vendor links AND nothing client/portal-ish, hard-fail early
    if wp_present:
        has_clientish = any(_is_clientish_path(h, site_host) for _, h in links)
        if not has_clientish:
            return False, "WP login present; no vendor or client/portal paths."

    # PAGE TEXT: accept only strong phrases (generic login text is ignored in free text)
    page_text = soup.get_text(separator=" ", strip=True).lower()
    for kw in STRONG_TEXT_KEYWORDS:
        if kw in page_text:
            return True, f'Found text match "{kw}" on {base_url}'

    # LINK/BUTTON TEXT: allow strong or generic words but require vendor URL OR client/portal-ish path
    for text, abs_href in links:
        if _is_wp_login_url(abs_href):
            continue

        has_loginish_text = any(kw in text for kw in STRONG_TEXT_KEYWORDS) or any(w in text for w in GENERIC_LOGIN_WORDS)
        if not has_loginish_text:
            continue

        if _is_vendor_url(abs_href) or _is_clientish_path(abs_href, site_host):
            return True, f'Found portal link/button "{text}" → {abs_href}'

        # If URL is obviously generic auth (e.g., /login) without client/portal hints, ignore
        try:
            p = urlparse(abs_href)
            path = (p.path or "").lower()
            if any(path.endswith(g) or path == g for g in GENERIC_AUTH_PATHS):
                continue
        except Exception:
            pass

    # CLICKABLE (no href): only strong phrases; still ignored if the page is WP-only
    for tag in soup.find_all(["button", "span", "div"]):
        label = _norm(tag.get_text())
        if any(kw in label for kw in STRONG_TEXT_KEYWORDS):
            if wp_present:
                # require some client/portal path or vendor link on page to avoid WP-only false positives
                has_clientish = any(_is_clientish_path(h, site_host) for _, h in links) or any(_is_vendor_url(h) for _, h in links)
                if not has_clientish:
                    continue
            return True, f'Found clickable label "{label}" on {base_url}'

    return False, "No client-portal signals found."

def check_client_portal(url: str):
    """
    Reused structure, but now detects if the page is about a React job in the US.
    Returns (bool|None, message)
    """
    try:
        resp = _fetch(url)
        text = resp.text.lower()

        # Look for React mentions (avoid "reaction"/"reactive" false positives)
        has_react = any(
            kw in text for kw in ["react.js", "react js", "react developer", "frontend react", "react engineer", "react"]
        )

        # Look for US/Remote-US signals
        has_us = any(
            kw in text for kw in [
                "united states", "u.s.", "usa", "us only",
                "remote - us", "remote (us)", "remote within the us",
                "authorized to work in the us", "work authorization in the us"
            ]
        )

        if has_react and has_us:
            return True, "React job in the US found ✅"
        elif has_react:
            return False, "React job found, but US location not clear 🌎"
        else:
            return False, "No React job detected ❌"

    except requests.RequestException as e:
        return None, f"Request failed: {e}"

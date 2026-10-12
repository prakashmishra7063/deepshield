"""Web page analysis: impersonation and phishing heuristics plus media discovery."""
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from .base import Detector, MediaContext, Signal

BRANDS: dict[str, list[str]] = {
    "paypal": ["paypal.com"], "apple": ["apple.com", "icloud.com"],
    "microsoft": ["microsoft.com", "live.com", "office.com", "outlook.com", "microsoftonline.com"],
    "google": ["google.com", "gmail.com", "youtube.com"], "amazon": ["amazon.com", "amazon.in", "amazon.co.uk"],
    "facebook": ["facebook.com", "fb.com", "meta.com"], "instagram": ["instagram.com"],
    "whatsapp": ["whatsapp.com"], "netflix": ["netflix.com"], "linkedin": ["linkedin.com"],
    "tiktok": ["tiktok.com"], "coinbase": ["coinbase.com"], "binance": ["binance.com"],
    "metamask": ["metamask.io"], "dhl": ["dhl.com"], "fedex": ["fedex.com"], "usps": ["usps.com"],
    "chase": ["chase.com"], "wellsfargo": ["wellsfargo.com"], "hsbc": ["hsbc.com"], "x": ["x.com", "twitter.com"],
    "reddit": ["reddit.com"], "youtube": ["youtube.com"],
}
SECOND_LEVEL = {"co.uk", "com.au", "co.in", "co.jp", "com.br", "co.nz", "org.uk", "gov.uk", "ac.uk", "com.mx"}
HOMOGLYPHS = str.maketrans({"0": "o", "1": "l", "3": "e", "5": "s", "4": "a", "7": "t", "@": "a", "$": "s"})


def registrable_domain(host: str) -> str:
    parts = host.lower().rstrip(".").split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _lev(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _skeleton(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.translate(HOMOGLYPHS).replace("rn", "m").replace("vv", "w")


class PageParser(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.title = ""
        self._in_title = False
        self.meta: dict[str, str] = {}
        self.media: list[tuple[str, str]] = []
        self.forms: list[dict] = []
        self.password_fields = 0
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                self.meta[key] = a["content"][:2000]
        elif tag in ("img", "video", "audio", "source") and a.get("src"):
            kind = "image" if tag == "img" else ("video" if tag in ("video", "source") else "audio")
            self.media.append((kind, urljoin(self.base, a["src"])))
        elif tag == "form":
            self.forms.append({"action": urljoin(self.base, a.get("action", "")), "method": a.get("method", "get")})
        elif tag == "input" and a.get("type", "").lower() == "password":
            self.password_fields += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif len(self.text) < 2000:
            t = data.strip()
            if t:
                self.text.append(t[:300])


def parse_page(html: bytes, base_url: str) -> PageParser:
    p = PageParser(base_url)
    try:
        p.feed(html[:3_000_000].decode("utf-8", "ignore"))
    except Exception:
        pass
    return p


def discover_media(page: PageParser) -> list[tuple[str, str]]:
    """Primary media for a page: OpenGraph/Twitter cards first, then inline elements."""
    found: list[tuple[str, str]] = []
    for key, kind in (("og:video:secure_url", "video"), ("og:video", "video"), ("og:video:url", "video"),
                      ("og:image:secure_url", "image"), ("og:image", "image"), ("twitter:image", "image"),
                      ("og:audio", "audio")):
        if key in page.meta:
            found.append((kind, urljoin(page.base, page.meta[key])))
    found.extend(page.media)
    seen, out = set(), []
    for kind, u in found:
        if u not in seen and urlparse(u).scheme in ("http", "https"):
            seen.add(u)
            out.append((kind, u))
    return out[:5]


class WebImpersonationDetector(Detector):
    name = "web_impersonation"
    version = "1.0"
    kinds = ("html",)
    category = "heuristic"
    description = "Lookalike-domain, punycode and credential-harvesting checks for web pages."

    def run(self, ctx: MediaContext):
        url = ctx.source_url or ""
        u = urlparse(url)
        host = (u.hostname or "").lower()
        reg = registrable_domain(host)
        page = ctx.cache.get("page") or parse_page(ctx.data, url)
        title = page.title.strip()[:200]
        body = " ".join(page.text)[:20000].lower()
        facts = {"host": host, "registrable_domain": reg, "title": title, "password_fields": page.password_fields,
                 "forms": len(page.forms), "og_title": page.meta.get("og:title"), "og_site_name": page.meta.get("og:site_name")}
        signals: list[Signal] = []

        if "xn--" in host:
            try:
                uni = host.encode().decode("idna")
            except Exception:
                uni = host
            signals.append(Signal(self.name, "punycode", "Internationalized (punycode) domain", "moderate",
                                  "manipulated", f"The domain decodes to '{uni}'. Lookalike Unicode characters are a "
                                  "common impersonation technique.", category="impersonation",
                                  evidence={"host": host, "unicode": uni}))

        label = reg.split(".")[0]
        skel = _skeleton(label)
        claimed: str | None = None
        for brand, domains in BRANDS.items():
            if reg in domains:
                claimed = None
                break
            in_subdomain = brand in host[: -len(reg)] if len(brand) >= 4 else False
            if len(brand) >= 4 and (skel == brand or (len(brand) >= 6 and _lev(skel, brand) == 1) or in_subdomain):
                claimed = brand
        if claimed:
            signals.append(Signal(self.name, "lookalike_domain", f"Domain imitates '{claimed}'", "moderate",
                                  "manipulated", f"'{host}' resembles {claimed}'s official domains "
                                  f"({', '.join(BRANDS[claimed])}) but is not one of them.", category="impersonation",
                                  evidence={"host": host, "brand": claimed}))

        mentioned = [b for b in BRANDS if len(b) >= 4 and (b in title.lower() or b in (page.meta.get("og:site_name") or "").lower())]
        official = any(reg in BRANDS[b] for b in mentioned)
        if page.password_fields and mentioned and not official:
            signals.append(Signal(self.name, "brand_credential_form", "Login form under another brand's name",
                                  "moderate", "manipulated", f"The page presents itself as {', '.join(mentioned)} and asks "
                                  f"for a password, but it is hosted on {reg}.", category="impersonation",
                                  evidence={"brands": mentioned, "domain": reg}))
        if page.password_fields and u.scheme == "http":
            signals.append(Signal(self.name, "insecure_password", "Password requested over unencrypted HTTP", "moderate",
                                  "manipulated", "Legitimate services never collect passwords without HTTPS.",
                                  category="impersonation"))
        foreign = [f["action"] for f in page.forms if f["action"] and urlparse(f["action"]).hostname
                   and registrable_domain(urlparse(f["action"]).hostname) != reg]
        if foreign and page.password_fields:
            signals.append(Signal(self.name, "offsite_form", "Credentials posted to another domain", "weak",
                                  "manipulated", "A form on this page submits to a different domain.",
                                  category="impersonation", evidence={"actions": foreign[:3]}))
        urgency = re.findall(r"\b(verify your account|account (?:has been )?suspended|unusual activity|act now|"
                             r"confirm your identity|seed phrase|recovery phrase|gift card)\b", body)
        if urgency and (page.password_fields or claimed):
            signals.append(Signal(self.name, "pressure_language", "Pressure or credential-harvesting language", "weak",
                                  "manipulated", "The page uses phrases common in phishing lures.",
                                  category="impersonation", evidence={"phrases": sorted(set(urgency))[:5]}))
        return self.report(signals=signals, facts=facts)

"""Live evidence from Amazon.in, Flipkart and Myntra. Playwright drives your installed Chrome.

  collect(goal)      search the three sites for the goal, read up to 4 results each, open up to 2 product pages each
  latest()           the last collection, if any (output/live/latest.json)

What it does not do: log in, add to cart, or order. What it cannot see on a search page: size, stock, delivery,
returns, shipping and the checkout total; those stay listed as unverified. If a site shows no results (captcha,
layout change), it falls back to a Bing site: search and labels that evidence as a fallback.

Needs: pip install -r requirements-live.txt   (Playwright; uses your Chrome, no browser download)
"""
import hashlib
import importlib.util
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlparse

OUT = Path(__file__).resolve().parent.parent / "output" / "live"
SAMPLE = Path(__file__).resolve().parent.parent / "data" / "live-sample.json"
SITES = [
    {"name": "Amazon", "host": "amazon.in", "url": "https://www.amazon.in/s?k={q}"},
    {"name": "Flipkart", "host": "flipkart.com", "url": "https://www.flipkart.com/search?q={q}"},
    {"name": "Myntra", "host": "myntra.com", "url": "https://www.myntra.com/{slug}?sort=price_asc"},
]
FRESH_SECONDS = 15 * 60
UNVERIFIED = ["size", "stock", "delivery", "returns", "shipping", "checkout_total"]

# Runs inside the page: one extractor per site.
EXTRACT = r"""market => {
  const price = t => { const m = t.match(/(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)/i); return m ? Number(m[1].replaceAll(',', '')) : null; };
  const arr = [];
  if (market === 'Amazon') for (const el of document.querySelectorAll('[data-component-type="s-search-result"]')) {
    const a = el.querySelector('a:has(h2),h2 a,a.a-link-normal.s-no-outline'), h = el.querySelector('h2'), pr = el.querySelector('.a-price .a-offscreen');
    if (a && h && pr) arr.push({product_name: [...el.querySelectorAll('h2')].map(e => e.innerText.trim()).join(' '), source_url: a.href,
                                observed_price_inr: price(pr.innerText), source_excerpt: el.innerText.slice(0, 1100)});
  }
  if (market === 'Flipkart') for (const a of document.querySelectorAll('a[href*="/p/"]')) {
    let el = a; for (let i = 0; i < 3 && el.parentElement; i++) { if (price(el.innerText) && el.innerText.length > 60) break; el = el.parentElement; }
    const v = price(el.innerText);
    if (v && a.href) arr.push({product_name: (a.title || a.innerText || el.innerText).slice(0, 220), source_url: a.href, observed_price_inr: v, source_excerpt: el.innerText.slice(0, 1100)});
  }
  if (market === 'Myntra') for (const el of document.querySelectorAll('li.product-base')) {
    const a = el.querySelector('a'), pr = el.querySelector('.product-discountedPrice,.product-price');
    const pm = pr?.innerText.match(/(?:Rs\.?|₹)\s*([\d,]+(?:\.\d{1,2})?)/i); const v = pm ? Number(pm[1].replaceAll(',', '')) : null;
    if (a && v) arr.push({product_name: [...el.querySelectorAll('h3,h4')].map(e => e.innerText).join(' '), source_url: a.href, observed_price_inr: v, source_excerpt: el.innerText.slice(0, 1100)});
  }
  return arr;
}"""
DETAIL = r"""market => {
  const txt = sel => [...document.querySelectorAll(sel)].map(e => e.innerText.trim()).filter(Boolean).join('\n');
  if (market === 'Amazon') return {name: txt('#productTitle'), details: txt('#variation_color_name .selection, #productDetails_techSpec_section_1, #productDetails_detailBullets_sections1, #productOverview_feature_div, #detailBullets_feature_div, #feature-bullets'),
                                   priceText: txt('#corePriceDisplay_desktop_feature_div .a-price .a-offscreen, #corePrice_feature_div .a-price .a-offscreen')};
  if (market === 'Flipkart') return {name: txt('h1'), details: txt('table').slice(0, 7000), priceText: ''};
  return {name: txt('.pdp-title, .pdp-name'), details: txt('.pdp-product-description-content, .index-tableContainer').slice(0, 7000), priceText: txt('.pdp-price strong')};
}"""
BING = r"""els => els.map(el => ({product_name: el.querySelector('h2')?.innerText || '', source_url: el.querySelector('h2 a')?.href || '', source_excerpt: el.innerText.slice(0, 1100)}))"""


def now():
    return datetime.now(timezone.utc).isoformat()


def on_host(url, host):
    try:
        h = urlparse(url).hostname or ""
        return urlparse(url).scheme == "https" and (h == host or h.endswith("." + host))
    except ValueError:
        return False


def price_in(text, lowest=False):
    """The first price in the text, or the lowest one (a product page shows the M.R.P. and the deal price)."""
    found = [float(m.replace(",", "")) for m in re.findall(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)", text or "", re.I)]
    return (min(found) if lowest else found[0]) if found else None


def _clean_url(site, url):
    u = urlparse(url)
    if site == "Amazon":
        if u.path == "/sspa/click":                       # sponsored link: the real product is in ?url=
            inner = parse_qs(u.query).get("url", [None])[0]
            if inner:
                u = urlparse(urljoin(f"{u.scheme}://{u.netloc}", inner))
        m = re.search(r"/dp/([A-Z0-9]{10})", u.path)
        if m:
            return f"{u.scheme}://{u.netloc}/dp/{m[1]}"
    return u.geturl()


def words(goal):
    """What the store's search box gets: colour, type, "shoes". Size isn't searchable on these pages."""
    return " ".join(w for w in (goal.get("color"), goal.get("type"), "shoes") if w)


def search_text(goal):
    return f"{words(goal)} under {goal['max_price']}"


class Stopped(Exception):
    """Someone pressed Stop during a collection. Chrome closes; nothing is saved."""


def collect(goal, headless=None, progress=lambda text: None, stop=lambda: False):
    """Search the three sites in your Chrome for the goal (colour, type, budget). Returns the evidence dict and
    saves it to output/live/. stop() is checked before each site and each product page."""
    from playwright.sync_api import sync_playwright
    headless = os.getenv("MARKETPLACE_BROWSER_HEADLESS", "0") == "1" if headless is None else headless
    budget, query = goal["max_price"], search_text(goal)
    start, candidates, sources = time.time(), [], []
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=headless)
        # Headless Chrome says "HeadlessChrome" in its user agent and some sites refuse it; send the normal one.
        probe = browser.new_page()
        agent = probe.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
        probe.close()
        context = browser.new_context(locale="en-IN", viewport={"width": 1400, "height": 900}, user_agent=agent)
        try:
            for site in SITES:
                if stop():
                    raise Stopped()
                name, host = site["name"], site["host"]
                url = site["url"].format(q=quote(query), slug=words(goal).replace(" ", "-"))
                progress(f"Searching {name}…")
                page = context.new_page()
                status, items, title, error, observed_at = "NO_EXTRACTABLE_CANDIDATES", [], "", None, now()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=22000)
                    page.wait_for_timeout(1800)
                    title = page.title()
                    items = page.evaluate(EXTRACT, name)
                    if not items:                          # results can render late: look once more
                        page.wait_for_timeout(2500)
                        items = page.evaluate(EXTRACT, name)
                    page.screenshot(path=str(OUT / f"{name.lower()}-latest.png"))   # what the store itself showed
                    body = page.locator("body").inner_text()[:2500]
                    if any(w in body.lower() for w in ("captcha", "robot", "access denied", "maintenance")):
                        status = "BLOCKED_OR_UNAVAILABLE"
                    if items:
                        status = "OK"
                    else:                                  # labelled fallback: a search engine's index of the site
                        progress(f"{name}: nothing readable, trying a Bing site: search…")
                        page.goto("https://www.bing.com/search?q=" + quote(f"site:{host} {query} price"),
                                  wait_until="domcontentloaded", timeout=18000)
                        page.wait_for_timeout(1300)
                        for row in page.locator("li.b_algo").evaluate_all(BING):
                            v = price_in(row["source_excerpt"])
                            if on_host(row["source_url"], host) and v:
                                items.append({**row, "observed_price_inr": v, "evidence_mode": "search_index_fallback"})
                        if items:
                            status = "SEARCH_INDEX_FALLBACK"
                except Exception as e:                    # one site failing never stops the others
                    error, status = type(e).__name__, "SOURCE_ERROR"
                seen, good = set(), []
                for x in items:
                    try:
                        x["source_url"] = _clean_url(name, x["source_url"])
                    except ValueError:
                        continue
                    v = x.get("observed_price_inr")
                    if x["source_url"] in seen or not v or v <= 0 or not on_host(x["source_url"], host):
                        continue
                    seen.add(x["source_url"])
                    good.append(x)
                good = good[:4]
                for x in [g for g in good if g["observed_price_inr"] <= budget][:2]:   # read the product page
                    if stop():
                        raise Stopped()
                    progress(f"{name}: reading a product page…")
                    detail, x["detail_status"] = context.new_page(), "UNAVAILABLE"
                    try:
                        detail.goto(x["source_url"], wait_until="domcontentloaded", timeout=12000)
                        detail.wait_for_timeout(1000)
                        if not on_host(detail.url, host):
                            raise RuntimeError("redirect outside the allowlist")
                        d = detail.evaluate(DETAIL, name)
                        if d.get("name"):
                            x["product_name"], x["source_url"] = d["name"], detail.url
                            x["source_excerpt"] = (x["source_excerpt"] + "\nPRODUCT PAGE: " + d["name"] + "\n" + d["details"])[:8000]
                            x["observed_at"], x["detail_status"] = now(), "OBSERVED"
                            if price_in(d.get("priceText"), lowest=True):
                                x["observed_price_inr"] = price_in(d["priceText"], lowest=True)
                    except Exception as e:
                        x["detail_status"] = "ERROR_" + type(e).__name__
                    finally:
                        detail.close()
                for x in good:
                    candidates.append({**x, "offer_id": name[:3].upper() + "-" + hashlib.sha256(x["source_url"].encode()).hexdigest()[:10],
                                       "marketplace": name, "observed_at": x.get("observed_at") or observed_at,
                                       "evidence_mode": x.get("evidence_mode", "retailer_page"), "unverified_fields": UNVERIFIED})
                sources.append({"marketplace": name, "search_url": url, "title": title, "observed_at": observed_at,
                                "status": status, "candidate_count": len(good), "error": error})
                progress(f"{name}: {len(good)} listings ({status.lower().replace('_', ' ')})")
                page.close()
        finally:
            browser.close()
    evidence = {"mode": "live_browser", "search_provider": "Playwright + system Chrome", "query": query, "budget": budget,
                "goal": {k: goal.get(k) for k in ("color", "type", "max_price")},
                "observed_at": now(), "candidates": candidates, "sources": sources, "visible_browser": not headless,
                "duration_ms": round((time.time() - start) * 1000),
                "limitations": ["Observed item prices are not verified checkout totals.",
                                "Search-index fallback is labelled explicitly.", "Missing evidence is never invented."]}
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    for f in (OUT / f"{stamp}.json", OUT / "latest.json"):
        f.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    from lab import trace
    trace.prune(OUT, "20[0-9][0-9]-*.json", 10)   # keep the last 10 collections
    return evidence


def forget():
    """Drop the saved collection (latest.json and the screenshots): the next live run collects again.
    The timestamped history in output/live/ stays."""
    for f in [OUT / "latest.json"] + [OUT / f"{s['name'].lower()}-latest.png" for s in SITES]:
        f.unlink(missing_ok=True)


def latest(sample=True):
    """The last collection: output/live/latest.json, else (sample=True) the recording shipped in data/."""
    for f in (OUT / "latest.json", SAMPLE) if sample else (OUT / "latest.json",):
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    return None


def age_seconds(evidence):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(evidence["observed_at"])).total_seconds()


def available():
    return importlib.util.find_spec("playwright") is not None

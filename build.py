#!/usr/bin/env python3
"""
Convert the wget-mirrored Wix site into a static site for GitHub Pages.

Reads the pristine page HTML from SRC_DIR, pulls image assets from the wget mirror
(falling back to the network), strips Wix branding and all JavaScript, swaps the
non-redistributable fonts for open-licensed substitutes, and writes OUT_DIR.

Re-runnable: OUT_DIR is rebuilt from scratch each time.
"""
import glob, hashlib, os, re, shutil, subprocess, urllib.parse

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — the only things you should need to edit
# ─────────────────────────────────────────────────────────────────────────────

# Your domain, once you've bought it back. Leave "" until then: the site works
# fine on github.io without it (only canonical/og:url tags need an absolute URL).
SITE_DOMAIN = "graciousmoosedesigns.com"

# Address the contact page should point at. Leave "" to render the forms
# visually intact but disabled, with a TODO comment in the markup.
CONTACT_EMAIL = "hello@graciousmoosedesigns.com"

# Font substitutions. Swap these names/files to change the look.
# "Gracious" and all six section headings share one face; the "Moose" half of the
# wordmark gets its own.
FONT_HEADING  = ("Shadows Into Light", "shadows-into-light-400-normal-0.woff2")  # Allenattore + Moon Flower headings
FONT_WORDMARK = ("Grand Hotel", "grand-hotel-400-normal-0.woff2")               # "Moose" in the wordmark only
FONT_BODY     = ("Mulish", {300: "mulish-300-normal-0.woff2",
                            400: "mulish-400-normal-1.woff2",
                            600: "mulish-600-normal-2.woff2"})        # replaces Avenir LT
FONT_SERIF    = ("Libre Baskerville", {400: "libre-baskerville-400-normal-1.woff2",
                                       700: "libre-baskerville-700-normal-2.woff2"})  # kept, OFL

SITE_TITLE = "Gracious Moose Designs"

# Text fixes. The odd capitalisation existed to coax decorative glyphs out of
# Moon Flower; with a normal face it just reads as a typo.
TEXT_FIXES = {
    "EXPlore DESIGNS": "Explore Designs",
    "GraciousMooseDesigns": "Gracious Moose Designs",
}

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
HERE     = os.path.dirname(os.path.abspath(__file__))
# Everything the build needs is archived in the repo, so it does not depend on the
# Wix site still existing. See SETUP.md → "Source material".
SOURCE   = os.path.join(HERE, "source")
SRC_DIR    = os.path.join(SOURCE, "orig")         # desktop page HTML
SRC_MOBILE = os.path.join(SOURCE, "orig-mobile")  # mobile page HTML (Wix serves a distinct render)
MIRROR   = os.path.join(SOURCE, "raw")            # wget mirror, primary asset source
CACHE    = os.path.join(SOURCE, "assets-cache")   # assets the mirror lacks (mobile crops)
FONT_DIR = os.path.join(SOURCE, "gf")             # OFL woff2 files
OUT_DIR  = os.path.join(HERE, "docs")             # GitHub Pages "deploy from /docs"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# slug in the mirror -> output path
PAGES = {
    "index":                "index.html",
    "about":                "about/index.html",
    "explore-designs":      "explore-designs/index.html",
    "notecards-stationery": "notecards-stationery/index.html",
    "christmas":            "christmas/index.html",
    "get-in-touch":         "get-in-touch/index.html",
}

ASSET_HOSTS = ("static.wixstatic.com", "static.parastorage.com",
               "siteassets.parastorage.com", "video.wixstatic.com")

# Any asset URL containing one of these is a font we must not redistribute.
FONT_PATH_MARKERS = ("/fonts/", "/ufonts/", "fonts-cache", "user-site-fonts")

# Wix font family tokens -> what to do with them.
MOOSE_HASH, GRACIOUS_HASH = "c96f6f5c", "772a84c0"
DROP_FAMILY_PATTERNS = (r"helvetica", r"madefor", r"din-next", r"wixfreemiumfont")

# The '|' exclusion matters: data-gm-slides holds a pipe-separated URL list, and
# without it a single match runs straight through the separators and swallows the
# whole list as one URL.
URL_RE = re.compile(
    r"(?:https?:)?//(?:" + "|".join(h.replace(".", r"\.") for h in ASSET_HOSTS)
    + r")/[^\s\"'()<>\\|]+")

stats = {"assets": 0, "mirror": 0, "cached": 0, "downloaded": 0, "failed": []}


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────
def log(msg):
    print(msg, flush=True)


def strip_tags_balanced(html, tag, attr_match):
    """Remove every <tag ...attr_match...>…</tag>, honouring nesting."""
    out, i = html, 0
    pattern = re.compile(r"<" + tag + r"\b[^>]*" + attr_match + r"[^>]*>", re.I)
    while True:
        m = pattern.search(out)
        if not m:
            return out
        depth, j = 1, m.end()
        open_re  = re.compile(r"<" + tag + r"\b", re.I)
        close_re = re.compile(r"</" + tag + r"\s*>", re.I)
        while depth > 0 and j < len(out):
            no = open_re.search(out, j)
            nc = close_re.search(out, j)
            if not nc:
                j = len(out)
                break
            if no and no.start() < nc.start():
                depth += 1
                j = no.end()
            else:
                depth -= 1
                j = nc.end()
        out = out[:m.start()] + out[j:]
        i += 1
        if i > 50:
            return out


def cache_path(url):
    """Where wget would have stored this URL (--restrict-file-names=windows)."""
    p = urllib.parse.urlparse("https:" + url if url.startswith("//") else url)
    return os.path.join(MIRROR, p.netloc, urllib.parse.unquote(p.path.lstrip("/")))


def local_name(url):
    p = urllib.parse.urlparse("https:" + url if url.startswith("//") else url)
    base = urllib.parse.unquote(os.path.basename(p.path)) or "asset"
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-.") or "asset"
    root, ext = os.path.splitext(base)
    if not ext:
        ext = ".bin"
    return f"{hashlib.sha1(url.encode()).hexdigest()[:10]}-{root[:60]}{ext}"


def fetch_asset(url, dest):
    """Resolve an asset from the archive, only touching the network as a last resort.

    Order: wget mirror -> local cache -> live site. Anything fetched from the
    network is written into the cache, so the next build is fully offline even if
    the original site has gone.
    """
    src = cache_path(url)
    if os.path.isfile(src) and os.path.getsize(src) > 0:
        shutil.copyfile(src, dest)
        stats["mirror"] += 1
        return True

    cached = os.path.join(CACHE, os.path.basename(dest))
    if os.path.isfile(cached) and os.path.getsize(cached) > 0:
        shutil.copyfile(cached, dest)
        stats["cached"] += 1
        return True

    full = "https:" + url if url.startswith("//") else url
    r = subprocess.run(["curl", "-sSL", "-A", UA, "--max-time", "60", full, "-o", dest],
                       capture_output=True)
    if r.returncode == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 0:
        os.makedirs(CACHE, exist_ok=True)
        shutil.copyfile(dest, cached)          # archive it for next time
        stats["downloaded"] += 1
        return True
    stats["failed"].append(url)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# font CSS
# ─────────────────────────────────────────────────────────────────────────────
def copy_fonts():
    """Copy the OFL substitutes into the build and return their web paths."""
    dest = os.path.join(OUT_DIR, "assets", "fonts")
    os.makedirs(dest, exist_ok=True)
    used = {}
    files = ([FONT_HEADING[1], FONT_WORDMARK[1]]
             + list(FONT_BODY[1].values()) + list(FONT_SERIF[1].values()))
    for fn in files:
        src = os.path.join(FONT_DIR, fn)
        if not os.path.isfile(src):
            log(f"  !! missing font file {fn}")
            continue
        shutil.copyfile(src, os.path.join(dest, fn))
        used[fn] = f"/assets/fonts/{fn}"
    # The OFL requires the licence to travel with the font files. source/gf/ holds
    # the whole candidate pool from the font review, so ship only the licences for
    # the faces actually deployed — deriving the family slug from the filename
    # ("shadows-into-light-400-normal-0.woff2" -> "shadowsintolight").
    for fn in used:
        fam = re.sub(r"-\d+.*$", "", fn).replace("-", "")
        lic = os.path.join(HERE, "licenses", f"OFL-{fam}.txt")
        if os.path.isfile(lic):
            shutil.copyfile(lic, os.path.join(dest, os.path.basename(lic)))
        else:
            log(f"  !! no licence found for {fam} ({fn}) — add licenses/OFL-{fam}.txt")
    return used


def build_font_css(tokens, webpaths):
    """
    Emit @font-face rules that keep Wix's family NAMES but point at our substitutes.
    That way the site's existing thousands of font-family declarations keep working
    and we never have to rewrite them.
    """
    css = ["\n/* ---- open-licensed font substitutions (see FONTS.md) ---- */"]

    def rule(family, path, weight=400, style="normal"):
        return (f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:{style};"
                f"font-display:swap;src:url('{path}') format('woff2');}}")

    # Both brand faces collapse onto one heading font; the wordmark's "Moose" is
    # re-pointed at FONT_WORDMARK afterwards, per-element.
    for tok in sorted(tokens["moose"]) + sorted(tokens["gracious"]):
        css.append(rule(tok, webpaths.get(FONT_HEADING[1], "")))

    # Avenir -> body sans, mapping Wix's light/heavy naming onto real weights
    for tok in sorted(tokens["avenir"]):
        heavy = any(k in tok.lower() for k in ("heavy", "85", "black", "bold"))
        wf = FONT_BODY[1][600 if heavy else 300]
        css.append(rule(tok, webpaths.get(wf, ""), 600 if heavy else 300))

    # Libre Baskerville, self-hosted from the OFL release
    for weight, fn in FONT_SERIF[1].items():
        css.append(rule("libre baskerville", webpaths.get(fn, ""), weight))
        css.append(rule("Libre Baskerville", webpaths.get(fn, ""), weight))

    # our own families, so new CSS can reference them directly
    css.append(rule(FONT_HEADING[0], webpaths.get(FONT_HEADING[1], "")))
    css.append(rule(FONT_WORDMARK[0], webpaths.get(FONT_WORDMARK[1], "")))
    for weight, fn in FONT_BODY[1].items():
        css.append(rule(FONT_BODY[0], webpaths.get(fn, ""), weight))

    # neutralise the JS-injected banner offset and give Helvetica/Madefor a sane stack
    css.append(":root{--wix-ads-height:0px !important;}")
    css.append("#WIX_ADS{display:none !important;}")
    css.append(NAV_CSS)
    return "\n".join(css)


def collect_font_tokens(html):
    toks = {"moose": set(), "gracious": set(), "avenir": set()}
    for m in re.finditer(r"\b((?:wfont_|wf_)[0-9a-f_]+)\b", html):
        t = m.group(1)
        if MOOSE_HASH in t:
            toks["moose"].add(t)
        elif GRACIOUS_HASH in t:
            toks["gracious"].add(t)
    for m in re.finditer(r"\b(avenir-lt-w\d+_\d+-[a-z]+\d*)\b", html, re.I):
        toks["avenir"].add(m.group(1))
    return toks


def element_span(html, start):
    """Given the index of a '<div' opening tag, return (start, end) of the subtree."""
    open_end = html.find(">", start)
    if open_end == -1:
        return None
    depth, j = 1, open_end + 1
    while depth and j < len(html):
        nxt = re.compile(r"<div\b|</div\s*>").search(html, j)
        if not nxt:
            return None
        depth += -1 if nxt.group(0).startswith("</") else 1
        j = nxt.end()
    return (start, j)


def wire_gallery(html):
    """Make the "Featured designs" carousel work.

    Wix rendered only the first two slides and fetched the rest on demand, and the
    arrows and thumbnails were driven by its React runtime — so statically nothing
    moved. The thumbnail strip does contain every item, and a thumbnail URL differs
    from its full-size slide only in the transform (w_120,h_120,q_70 against the
    slide's own w_696,h_402,q_90). So derive a slide URL per thumbnail and record
    the list on the gallery root for the shim to drive.

    Only galleries with a thumbnail strip are touched; the grid galleries on the
    other pages render every item already and need nothing.
    """
    # class="pro-gallery" exactly: the nested #pro-gallery-container-… also starts
    # with "pro-gallery-", and matching both meant editing a parent and its child.
    edits = []
    for m in re.finditer(r'<div\b[^>]*id="pro-gallery-[^"]*"[^>]*class="pro-gallery"[^>]*>', html):
        span = element_span(html, m.start())
        if not span:
            continue
        region = html[span[0]:span[1]]
        if "thumbnailItem" not in region:
            continue

        # the slide transform this gallery uses, from an already-rendered item
        dims = re.search(r"/v1/fill/w_(\d+),h_(\d+),q_90", region)
        if not dims:
            continue
        sw, sh = dims.group(1), dims.group(2)

        slides, slides2x = [], []
        for t in re.finditer(
                r'class="thumbnailItem[^"]*"[^>]*?background-image:\s*url\(([^)]+?)\)', region):
            url = t.group(1).strip("'\" ")

            def at(w, h, u=url):
                # swap the thumbnail's transform for the slide's, keeping any focal point
                s = re.sub(r"w_\d+,h_\d+", f"w_{w},h_{h}", u)
                return re.sub(r"\bq_\d+", "q_90", s)

            slides.append(at(sw, sh))
            slides2x.append(at(int(sw) * 2, int(sh) * 2))   # Wix served 2x; keep retina sharp
        if len(slides) < 2:
            continue
        edits.append((m.start(), m.end(), m.group(0)[:-1]
                      + ' data-gm-slides="' + "|".join(slides) + '"'
                      + ' data-gm-slides-2x="' + "|".join(slides2x) + '">'))

    # apply back-to-front so earlier offsets stay valid
    for start, end, replacement in reversed(edits):
        html = html[:start] + replacement + html[end:]
    return html, len(edits)


FORM_DROP = ("last-name", "phone", "address")   # fields to remove
FORM_KEEP = ("first-name", "email")             # fields to widen to the full column
FORM_RELABEL = {"First Name": "Name"}


def remove_element_by_id(html, el_id):
    """Balanced removal of the <div id="el_id"> … </div> subtree."""
    m = re.search(r'<div\b[^>]*id="' + re.escape(el_id) + r'"[^>]*>', html)
    if not m:
        return html, False
    depth, j = 1, m.end()
    while depth and j < len(html):
        nxt = re.compile(r"<div\b|</div\s*>").search(html, j)
        if not nxt:
            break
        depth += -1 if nxt.group(0).startswith("</") else 1
        j = nxt.end()
    return html[: m.start()] + html[j:], True


def simplify_form(html):
    """Reduce the contact form to Name / Email / Message.

    Wix lays the form out on a grid whose rows are `min-content`, so deleting a
    field collapses its row and leaves no gap — no need to rewrite the template.
    Name and Email were half-width because Last Name and Phone sat beside them, so
    both are widened to whatever width the message field declares. That value is
    read from the page rather than hardcoded, because the desktop and mobile
    variants use different ones (510px vs the narrower mobile column).
    """
    if "<form" not in html:
        return html, 0

    form_html = re.search(r"<form\b.*?</form>", html, re.S).group(0)

    # input name -> wrapper id, via Wix's own "input_<wrapperId>" convention
    wrappers = {}
    for m in re.finditer(r"<(?:input|textarea)\b[^>]*>", form_html):
        tag = m.group(0)
        eid = re.search(r'id="([^"]*)"', tag)
        if not eid:
            continue
        name = re.search(r'name="([^"]*)"', tag)
        wrappers[name.group(1) if name else "message"] = re.sub(
            r"^(?:input|textarea)_", "", eid.group(1))

    # The message field spans the column, so reuse its declared width. Each component
    # gets several #id rules (custom properties, then geometry), so scan them all for
    # the one carrying a real `width` — the first block has none.
    WIDTH_RE = re.compile(r"(^|;)\s*width\s*:\s*([^;]+)")

    full = None
    if "message" in wrappers:
        for rule in re.finditer(r"#" + re.escape(wrappers["message"]) + r"\s*\{([^}]*)\}", html):
            w = WIDTH_RE.search(rule.group(1))
            if w:
                full = w.group(2).strip()
                break

    removed = 0
    for field in FORM_DROP:
        if field in wrappers:
            html, ok = remove_element_by_id(html, wrappers[field])
            removed += int(ok)

    if full:
        for field in FORM_KEEP:
            wid = wrappers.get(field)
            if not wid:
                continue
            html = re.sub(
                r"(#" + re.escape(wid) + r"\s*\{)([^}]*)(\})",
                lambda mm: mm.group(1)
                + WIDTH_RE.sub(lambda w: w.group(1) + f"width:{full}", mm.group(2))
                + mm.group(3),
                html)

    for old, new in FORM_RELABEL.items():
        html = html.replace(f'placeholder="{old}"', f'placeholder="{new}"')
        html = html.replace(f'aria-label="{old}"', f'aria-label="{new}"')

    return html, removed


def deblur_images(html):
    """Replace Wix's blurred low-quality placeholders with the real image.

    Wix ships a tiny blurred LQIP as the SSR `src` and swaps in the full image on
    hydration. With the JS gone the blur is what you see — most visibly the page
    background, a 253x288 placeholder stretched across the whole viewport. The real
    dimensions are in the sibling <wow-image data-image-info>, so rebuild the URL
    from those and let the asset pipeline localise it.
    """
    import html as html_mod
    import json

    # uri -> (source width, source height), from every data-image-info on the page
    dims = {}
    for m in re.finditer(r'data-image-info="([^"]*)"', html):
        try:
            d = json.loads(html_mod.unescape(m.group(1)))
            img = d.get("imageData", {})
            if img.get("uri") and img.get("width") and img.get("height"):
                dims[img["uri"]] = (int(img["width"]), int(img["height"]))
        except (ValueError, KeyError):
            continue

    MAX_W = 1920
    fixed = 0

    def repl(m):
        nonlocal fixed
        tag = m.group(0)
        src = re.search(r'src="([^"]*)"', tag)
        if not src:
            return tag
        uri = re.search(r"/media/([^/]+)/v1/", src.group(1))
        if not uri or uri.group(1) not in dims:
            return tag
        uri = uri.group(1)
        sw, sh = dims[uri]
        # Size from the element's own box. The page background carries width="1920";
        # small decorations carry none, and blindly fetching their 2300px source put
        # 20 MB of 8 MB PNGs into the build for images rendered at 49px. Fall back to
        # a modest upgrade of the placeholder instead.
        w_attr = re.search(r'\bwidth="(\d+)"', tag)
        # the transform sits in the segment after /v1/, e.g. /v1/fill/w_49,h_49,…
        placeholder = re.search(r"[/,]w_(\d+)", src.group(1))
        if w_attr:
            want = int(w_attr.group(1))
        elif placeholder:
            want = int(placeholder.group(1)) * 4
        else:
            want = 800
        w = max(1, min(sw, want, MAX_W))
        h = max(1, round(sh * w / sw))          # keep the source aspect: object-fit crops
        # plain JPEG rather than enc_avif: the extension would lie about the format
        new = (f"https://static.wixstatic.com/media/{uri}"
               f"/v1/fill/w_{w},h_{h},al_c,q_85/{uri}")
        fixed += 1
        return tag.replace(src.group(1), new)

    html = re.sub(r"<img\b[^>]*blur_\d+[^>]*>", repl, html)
    return html, fixed


def enable_submenu(html):
    """Turn the SSR submenu fallback into a real dropdown.

    Wix's runtime cloned submenu items into a JS-built panel (#…moreContainer, which
    ships empty). The <ul> left inside the menu item is an aria-hidden fallback with
    an *inline* display:none — inline beats any stylesheet, so it has to be stripped
    here rather than overridden in CSS. Without this, /notecards-stationery/ is
    unreachable from the navigation.
    """
    n = 0

    def fix(m):
        nonlocal n
        n += 1
        tag = m.group(0)
        tag = re.sub(r'\s*aria-hidden="true"', "", tag)
        tag = re.sub(r'\s*style="display:\s*none"', "", tag)
        return tag

    html = re.sub(r'<ul\b[^>]*aria-hidden="true"[^>]*style="display:\s*none"[^>]*>', fix, html)
    # the fallback links were taken out of the tab order because the JS panel owned it
    html = html.replace('class="" tabindex="-1"', 'class=""')
    return html, n


NAV_CSS = """
/* ---- navigation: reinstate what the Wix runtime used to do ---------------- */
/* Equal-width buttons. Wix records the intent in data-same-width-buttons /
   data-stretch-buttons-to-menu-width and then set inline widths from JS
   (245px each = the 980px menu / 4 items). Flex reproduces it with no script. */
wix-dropdown-menu > nav > ul { display: flex; }
wix-dropdown-menu > nav > ul > li.wixui-dropdown-menu__item { flex: 1 1 0; min-width: 0; }
/* The "More" overflow bucket, which Wix hid whenever every item fitted.
   !important is needed, not lazy: Wix's own rule for it is a four-class selector
   (.SiBgBF .Kefle8 .iTBB8q .QBNfeJ) and outranks anything we can write without
   depending on its hashed class names, which change if the site is re-mirrored. */
wix-dropdown-menu > nav > ul > li:not(.wixui-dropdown-menu__item) { display: none !important; }

/* The menu box computes `overflow: hidden auto` from Wix's stylesheet, which clips
   any dropdown to the 37px menu strip — so the panel never paints and its z-index
   never gets a say. Wix's runtime set overflow-x:visible here inline; do the same. */
wix-dropdown-menu { overflow: visible !important; }

/* The dropdown, from the SSR fallback list, styled with Wix's own custom
   properties so it tracks the menu's colours and font automatically. */
wix-dropdown-menu > nav > ul > li { position: relative; }
wix-dropdown-menu > nav > ul > li > ul {
  display: none; position: absolute; top: 100%; left: 0;
  min-width: 100%; margin: 0; padding: 0; list-style: none; z-index: 1000;
  background: rgba(var(--bgDrop, var(--color_11, 219, 219, 219)));
  border-radius: var(--rd, 0);
}
wix-dropdown-menu > nav > ul > li:hover > ul,
wix-dropdown-menu > nav > ul > li:focus-within > ul { display: block; }
wix-dropdown-menu > nav > ul > li > ul > li { display: block; }
wix-dropdown-menu > nav > ul > li > ul > li > a {
  /* 8px, not Wix's 14px: the substitute face is a little wider than Moon Flower,
     and this lands the panel on the parent's 245px instead of overhanging it. */
  display: block; height: 47px; line-height: 47px; padding: 0 8px;
  text-align: center; text-decoration: none; white-space: nowrap;
  font: var(--fnt, var(--font_1));
  color: rgb(var(--txt, var(--color_15, 96, 79, 91)));
}
wix-dropdown-menu > nav > ul > li > ul > li > a:hover,
wix-dropdown-menu > nav > ul > li > ul > li > a:focus-visible {
  color: rgb(var(--txth, var(--color_15, 96, 79, 91)));
  background: rgba(0, 0, 0, 0.05);
}

/* ---- mobile navigation --------------------------------------------------- */
/* #TINY_MENU ships an SEO-only link list which Wix's runtime kept out of sight
   while it drove a full-screen overlay from the hamburger. Left as-is the links
   spill down the header as raw blue text over the Instagram icon, and push the
   button 100px out of place. Hide the list, then reuse it as the actual menu. */
#TINY_MENU > ul { display: none; }
#TINY_MENU[data-gm-open="true"] > ul {
  display: block; position: absolute; top: 100%; right: 0; z-index: 1200;
  margin: 0; padding: 6px 0; list-style: none; min-width: 210px;
  background: #dbdbdb; box-shadow: 0 6px 18px rgba(0, 0, 0, 0.18);
}
/* descendant, not child: "Notecards & Stationery" and the Etsy link sit in a
   nested <ul> under Explore Designs, and child selectors left them unstyled at
   11px tall. The nested list is indented to keep that hierarchy legible. */
#TINY_MENU > ul li { display: block; }
#TINY_MENU > ul ul { margin: 0; padding: 0 0 0 16px; list-style: none; }
#TINY_MENU > ul a {
  display: block; padding: 12px 18px; text-decoration: none; white-space: nowrap;
  font-family: inherit; font-size: 17px; color: #604f5b;
}
#TINY_MENU > ul a:hover,
#TINY_MENU > ul a:focus-visible { background: rgba(0, 0, 0, 0.06); }

/* ---- featured-designs carousel ------------------------------------------ */
/* The thumbnails are click targets now, so they need to look like it, and the
   selected one needs to read as selected without Wix's runtime classes. */
[data-gm-slides] .thumbnailItem { cursor: pointer; opacity: 0.7; transition: opacity 0.2s ease; }
[data-gm-slides] .thumbnailItem:hover,
[data-gm-slides] .thumbnailItem:focus-visible { opacity: 0.92; }
[data-gm-slides] .thumbnailItem.pro-gallery-highlight { opacity: 1; outline: 2px solid rgba(96, 79, 91, 0.85); outline-offset: -2px; }
[data-gm-slides] button[data-hook^="nav-arrow"] { cursor: pointer; }
"""


def override_wordmark(html, moose_tokens):
    """Re-point just the wordmark's 'Moose' at FONT_WORDMARK.

    Every other use of the Moon Flower family stays on FONT_HEADING, so this has
    to be done per-element rather than in the @font-face layer.
    """
    if not moose_tokens:
        return html, 0
    # The element carrying font-family is an ancestor of the text: the word sits in
    # a nested <a>. So find spans styled with the Moon Flower stack, then look ahead
    # for "Moose" before any other visible text.
    tag_re = re.compile(
        r'<span\b[^>]*style="[^"]*font-family:[^"]*(?:'
        + "|".join(re.escape(t) for t in moose_tokens) + r')[^"]*"[^>]*>', re.I)
    out, pos, n = [], 0, 0
    for m in tag_re.finditer(html):
        lookahead = html[m.end():m.end() + 400]
        visible = re.sub(r"<[^>]*>", "", lookahead).replace("&nbsp;", " ").strip()
        if not visible.startswith("Moose"):
            continue
        tag = re.sub(r"font-family\s*:\s*[^;\"']+",
                     f"font-family:'{FONT_WORDMARK[0]}'", m.group(0))
        out.append(html[pos:m.start()])
        out.append(tag)
        pos = m.end()
        n += 1
    out.append(html[pos:])
    return "".join(out), n


def scrub_font_faces(html):
    """Delete @font-face blocks that point at fonts we may not redistribute."""
    def repl(m):
        blk = m.group(0)
        fam = re.search(r"font-family\s*:\s*[\"']?([^;\"'}]+)", blk)
        fam = (fam.group(1).strip().lower() if fam else "")
        if any(re.search(p, fam) for p in DROP_FAMILY_PATTERNS):
            return ""
        # anything still pointing at a Wix font URL goes; substitutes are appended later
        if any(mk in blk for mk in FONT_PATH_MARKERS):
            return ""
        return blk
    return re.sub(r"@font-face\s*\{[^}]*\}", repl, html, flags=re.S)


# ─────────────────────────────────────────────────────────────────────────────
# the shim: the few behaviours the stripped JS was providing
# ─────────────────────────────────────────────────────────────────────────────
# Wix serves a completely separate mobile render (viewport width=320, its own
# layout). Static hosting can't switch on User-Agent, so both variants are built
# and this picks between them client-side. It keys off screen.width rather than
# the viewport, because the two variants declare different viewport metas — using
# the viewport would make the choice self-confirming and could loop.
ROUTER_JS = """
(function () {
  try {
    var min = Math.min(window.screen.width, window.screen.height);
    var wantsMobile = min <= 500;
    var path = location.pathname;
    var onMobile = path === '/m' || path === '/m/' || path.indexOf('/m/') === 0;
    if (wantsMobile && !onMobile) {
      location.replace('/m' + path + location.search + location.hash);
    } else if (!wantsMobile && onMobile) {
      location.replace((path.replace(/^\\/m/, '') || '/') + location.search + location.hash);
    }
  } catch (e) { /* stay put rather than risk a loop */ }
})();
"""

SHIM_JS = """
/* Minimal replacements for the Wix runtime we removed. */
(function () {
  /* 1. Copyright year, kept current automatically. */
  var y = new Date().getFullYear();
  document.querySelectorAll('[data-current-year]').forEach(function (el) {
    el.textContent = y;
  });

  /* 2. Mobile nav. Wix's runtime opened a full-screen overlay from this button;
        instead we toggle the SEO link list, which the stylesheet turns into a
        dropdown panel. data-testid is Wix's own hook and survives a re-mirror,
        unlike the hashed class names. */
  var burger = document.querySelector('[data-testid="tinymenu-menubutton"]');
  var tiny = document.getElementById('TINY_MENU');
  if (burger && tiny) {
    var setOpen = function (open) {
      tiny.setAttribute('data-gm-open', open ? 'true' : 'false');
      burger.setAttribute('aria-expanded', open ? 'true' : 'false');
    };
    setOpen(false);
    burger.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      setOpen(tiny.getAttribute('data-gm-open') !== 'true');
    });
    document.addEventListener('click', function (e) {
      if (!tiny.contains(e.target)) setOpen(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') setOpen(false);
    });
  }

  /* 3. Forms. Wix handled submissions server-side; there is no backend now, so
        build a pre-filled message in the visitor's own mail client instead.
        A form with a textarea is the contact form; one without is the newsletter. */
  document.querySelectorAll('form[data-mailto]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var field = function (n) {
        var el = form.querySelector('[name="' + n + '"]');
        return el && el.value ? el.value.trim() : '';
      };
      var box = form.querySelector('textarea');
      var subject, lines = [];

      if (box) {
        var name = field('first-name');          /* relabelled "Name" in the markup */
        subject = 'Website enquiry' + (name ? ' from ' + name : '');
        [['Name', name], ['Email', field('email')]].forEach(function (pair) {
          if (pair[1]) lines.push(pair[0] + ': ' + pair[1]);
        });
        var msg = box.value.trim();
        if (msg) { lines.push(''); lines.push(msg); }
      } else {
        subject = 'Mailing list signup';
        lines.push('Please add this address to the mailing list:');
        lines.push('');
        lines.push(field('email'));
      }

      window.location.href = 'mailto:' + form.getAttribute('data-mailto')
        + '?subject=' + encodeURIComponent(subject)
        + '&body=' + encodeURIComponent(lines.join('\\n'));
    });
  });

  /* 4. The "Featured designs" carousel. build.py put every slide's URL on the
        gallery in data-gm-slides; drive the existing arrow and thumbnails from it.
        Wix only ever rendered two slides, so we swap the visible <img>'s src
        rather than trying to reconstruct its slide track. */
  document.querySelectorAll('[data-gm-slides]').forEach(function (gal) {
    var slides = (gal.getAttribute('data-gm-slides') || '').split('|').filter(Boolean);
    var slides2x = (gal.getAttribute('data-gm-slides-2x') || '').split('|').filter(Boolean);
    var thumbs = Array.prototype.slice.call(gal.querySelectorAll('.thumbnailItem'));
    var img = gal.querySelector('img');
    if (slides.length < 2 || !img) return;

    /* Wix left a second, off-frame item wrapper in the DOM. */
    var wrappers = gal.querySelectorAll('[id^="item-wrapper"]');
    for (var w = 1; w < wrappers.length; w++) wrappers[w].style.display = 'none';

    /* The img sits in a <picture>, whose <source srcset> beats any src we set —
       setting img.src alone changed the attribute but never the pixels. Drop the
       sources so the img's own srcset governs. */
    var pic = img.closest('picture');
    if (pic) Array.prototype.slice.call(pic.querySelectorAll('source')).forEach(function (s) { s.remove(); });

    var index = 0;
    var show = function (n) {
      index = (n + slides.length) % slides.length;
      img.removeAttribute('sizes');
      img.srcset = slides[index] + ' 1x' + (slides2x[index] ? ', ' + slides2x[index] + ' 2x' : '');
      img.src = slides[index];
      thumbs.forEach(function (t, k) {
        t.classList.toggle('pro-gallery-highlight', k === index);
        t.setAttribute('aria-current', k === index ? 'true' : 'false');
      });
    };

    var next = gal.querySelector('[data-hook="nav-arrow-next"]');
    if (next) next.addEventListener('click', function (e) { e.preventDefault(); show(index + 1); });

    /* Wix renders the back arrow only once you are past the first slide, so add one. */
    var prev = gal.querySelector('[data-hook="nav-arrow-prev"]');
    if (!prev && next) {
      prev = next.cloneNode(true);
      prev.setAttribute('data-hook', 'nav-arrow-prev');
      prev.setAttribute('aria-label', 'Previous Item');
      prev.style.right = 'auto';
      prev.style.left = next.style.right || '23px';
      prev.style.transform = 'scaleX(-1)';
      next.parentNode.insertBefore(prev, next);
      prev.addEventListener('click', function (e) { e.preventDefault(); show(index - 1); });
    }

    thumbs.forEach(function (t, k) {
      t.setAttribute('role', 'button');
      t.setAttribute('tabindex', '0');
      t.style.cursor = 'pointer';
      t.addEventListener('click', function (e) { e.preventDefault(); show(k); });
      t.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); show(k); }
      });
    });

    show(0);
  });

  /* 5. Wix marked some containers hidden until hydration; reveal them. */
  document.querySelectorAll('[style*="visibility:hidden"]').forEach(function (el) {
    if (el.closest('#WIX_ADS')) return;
    el.style.visibility = 'visible';
  });
})();
"""


# ─────────────────────────────────────────────────────────────────────────────
# per-page conversion
# ─────────────────────────────────────────────────────────────────────────────
def convert(slug, outpath, assets, mobile=False):
    src = SRC_MOBILE if mobile else SRC_DIR
    prefix = "/m" if mobile else ""          # link prefix for this variant
    html = open(os.path.join(src, slug + ".html"), encoding="utf-8", errors="replace").read()
    before = len(html)

    # --- 1. remove every script. This also removes accessToken / svSession /
    #        metaSiteId / Sentry DSNs, which only ever appear inside scripts.
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<script\b[^>]*/>", "", html, flags=re.I)
    html = re.sub(r"<noscript\b[^>]*>.*?</noscript>", "", html, flags=re.S | re.I)
    # Comments are all Wix build scaffolding ("BEGIN handleAccessTokens bundle",
    # "Sentry Loader Script", a commented-out wix.com mask-icon). Removing them
    # before asset collection also stops us fetching commented-out URLs.
    html = re.sub(r"<!--(?!\[if).*?-->", "", html, flags=re.S)
    html = re.sub(r"</link\s*>", "", html, flags=re.I)          # stray invalid closers
    html = re.sub(r"/\*#\s*sourceMappingURL=[^*]*\*/", "", html)

    # --- 2. Wix branding
    html = strip_tags_balanced(html, "div", r'id="WIX_ADS"')
    html = strip_tags_balanced(html, "div", r'class="[^"]*WIX_ADS')
    html = re.sub(r'<meta[^>]*name="generator"[^>]*>', "", html, flags=re.I)
    html = re.sub(r'<link[^>]*rel="(?:shortcut icon|icon|apple-touch-icon|mask-icon)"[^>]*>',
                  "", html, flags=re.I)
    html = re.sub(r'<link[^>]*rel="manifest"[^>]*>', "", html, flags=re.I)
    # resource hints and script preloads are pointless now, and several point at Wix
    html = re.sub(r'<link[^>]*rel="(?:preload|prefetch|preconnect|dns-prefetch|modulepreload)"[^>]*>',
                  "", html, flags=re.I)
    # any remaining anchor to wix.com becomes inert
    html = re.sub(r'<a\b([^>]*)href="https?://(?:www\.)?wix\.com[^"]*"([^>]*)>', r"<span\1\2>", html, flags=re.I)

    # --- 3. Wix inlines each component's CSS into a <style> tag and records the
    #        origin URL in data-href. The CSS is already here, so the attribute is
    #        just a dangling pointer at Wix's CDN — drop it.
    html = re.sub(r'(<style\b[^>]*?)\s+data-(?:href|url)="[^"]*"', r"\1", html, flags=re.I)

    # --- 3b. undo the things Wix's JS was responsible for painting
    html, n_blur = deblur_images(html)
    html, n_sub = enable_submenu(html)
    html, n_form = simplify_form(html)
    html, n_gal = wire_gallery(html)

    # --- 4. fonts
    tokens = collect_font_tokens(html)
    html = scrub_font_faces(html)
    html, n_wm = override_wordmark(html, tokens["moose"])

    # --- 4b. capitalisation and brand-name spacing. Text nodes only: a blind
    #         replace would rewrite the Etsy shop URL (.../shop/GraciousMooseDesigns)
    #         into one containing spaces.
    def fix_text_node(m):
        t = m.group(1)
        for wrong, right in TEXT_FIXES.items():
            t = t.replace(wrong, right)
        return ">" + t + "<"

    html = re.sub(r">([^<>]*)<", fix_text_node, html)

    # --- 4. rewrite asset URLs to local paths
    for url in sorted(set(URL_RE.findall(html)), key=len, reverse=True):
        if any(mk in url for mk in FONT_PATH_MARKERS):
            continue                       # licensed fonts: never shipped
        if url.endswith((".js", ".mjs", ".map", ".css")):
            continue
        web = assets.get(url)
        if web is None:
            name = local_name(url)
            dest = os.path.join(OUT_DIR, "assets", "media", name)
            if not os.path.isfile(dest) and not fetch_asset(url, dest):
                continue
            web = f"/assets/media/{name}"
            assets[url] = web
            stats["assets"] += 1
        html = html.replace(url, web)

    # strip any licensed-font url() that survived, so nothing 404s to Wix
    html = re.sub(r"url\((?:'|\")?(?:https?:)?//(?:static\.parastorage\.com|static\.wixstatic\.com)"
                  r"[^)]*?(?:'|\")?\)", "none", html)

    # --- 5. internal links -> clean paths, staying within this variant
    html = re.sub(r'href="(?:https?://amarissandersen\.wixsite\.com)?/mysite/([a-z0-9-]+)"',
                  rf'href="{prefix}/\1/"', html, flags=re.I)
    html = re.sub(r'href="(?:https?://amarissandersen\.wixsite\.com)?/mysite/?"',
                  f'href="{prefix}/"', html, flags=re.I)
    html = html.replace("https://amarissandersen.wixsite.com/mysite", prefix + "/")

    # --- 6. canonical / og:url. The mobile variant canonicalises to its desktop
    #        twin, and desktop advertises the mobile alternate: the standard
    #        separate-mobile-URL pattern, so the pair isn't read as duplicates.
    tail = "/" if slug == "index" else f"/{slug}/"
    html = re.sub(r'<link[^>]*rel="canonical"[^>]*>', "", html)
    if SITE_DOMAIN:
        base = f"https://{SITE_DOMAIN}"
        canonical = base + tail                      # always the desktop URL
        page_url = base + (prefix + tail)
        html = re.sub(r'(<meta[^>]*property="og:url"[^>]*content=")[^"]*(")',
                      rf"\g<1>{page_url}\g<2>", html)
        link = f'<link rel="canonical" href="{canonical}"/>'
        if not mobile:
            link += (f'<link rel="alternate" media="only screen and (max-width: 640px)" '
                     f'href="{base}/m{tail}"/>')
        html = html.replace("</head>", link + "\n</head>", 1)
    else:
        html = re.sub(r'<meta[^>]*property="og:url"[^>]*>', "", html)
        if not mobile:
            html = html.replace(
                "</head>",
                f'<link rel="alternate" media="only screen and (max-width: 640px)" '
                f'href="/m{tail}"/>\n</head>', 1)
    if mobile:
        html = re.sub(r'<meta[^>]*name="robots"[^>]*>', "", html, flags=re.I)

    # --- 7. copyright year
    html = re.sub(r"(©|&copy;)(\s|&nbsp;)*2020",
                  r'\1 <span data-current-year>2020</span>', html)

    # --- 8. forms
    # A plain <form action="mailto:" method="post"> is unreliable — Chrome largely
    # ignores it. So the form is tagged and the shim intercepts submit, building a
    # pre-filled mailto: from the fields. The action attribute stays as a no-JS
    # fallback so the mail client is at least offered.
    if CONTACT_EMAIL:
        html = re.sub(r"<form\b([^>]*)>",
                      rf'<form\1 action="mailto:{CONTACT_EMAIL}" data-mailto="{CONTACT_EMAIL}">',
                      html, flags=re.I)
    else:
        html = re.sub(r"<form\b([^>]*)>",
                      r"<!-- TODO: set CONTACT_EMAIL in build.py to wire this up -->"
                      r'<form\1 onsubmit="return false" aria-disabled="true">', html, flags=re.I)

    # --- 9. inject our CSS and shim
    font_css = build_font_css(tokens, assets["__fonts__"])
    html = html.replace("</head>", f"<style>{font_css}</style>\n</head>", 1)
    # Router goes as early as possible so a redirect happens before layout.
    html = re.sub(r"(<head[^>]*>)", rf"\1<script>{ROUTER_JS}</script>", html, count=1)
    html = html.replace("</body>", f"<script>{SHIM_JS}</script>\n</body>", 1)
    if "</body>" not in html:
        html += f"<script>{SHIM_JS}</script>"

    dest = os.path.join(OUT_DIR, outpath)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    open(dest, "w", encoding="utf-8").write(html)
    log(f"  {outpath:38s} {before // 1024:4d} KB -> {len(html) // 1024:4d} KB"
        f"   wordmark={n_wm} deblur={n_blur} submenu={n_sub} form-={n_form} carousel={n_gal}")
    return html


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(os.path.join(OUT_DIR, "assets", "media"), exist_ok=True)

    log("fonts:")
    webpaths = copy_fonts()
    log(f"  {len(webpaths)} substitute faces copied")

    assets = {"__fonts__": webpaths}
    log("desktop pages:")
    outputs = {slug: convert(slug, path, assets) for slug, path in PAGES.items()}
    log("mobile pages:")
    for slug, path in PAGES.items():
        convert(slug, "m/" + path, assets, mobile=True)

    # Pages housekeeping
    open(os.path.join(OUT_DIR, ".nojekyll"), "w").close()
    if SITE_DOMAIN:
        open(os.path.join(OUT_DIR, "CNAME"), "w").write(SITE_DOMAIN + "\n")
    open(os.path.join(OUT_DIR, "robots.txt"), "w").write(
        "User-agent: *\nAllow: /\n" + (f"Sitemap: https://{SITE_DOMAIN}/sitemap.xml\n" if SITE_DOMAIN else ""))
    if SITE_DOMAIN:
        urls = "".join(
            f"  <url><loc>https://{SITE_DOMAIN}/"
            f"{'' if s == 'index' else s + '/'}</loc></url>\n" for s in PAGES)
        open(os.path.join(OUT_DIR, "sitemap.xml"), "w").write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n")
    # 404 page reusing the homepage chrome. It must not claim to be the homepage,
    # so drop the canonical/alternate/og:url and mark it noindex — otherwise search
    # engines treat every bad URL as a duplicate of /.
    not_found = open(os.path.join(OUT_DIR, "index.html"), encoding="utf-8").read()
    not_found = re.sub(r'<link rel="canonical"[^>]*>', "", not_found)
    not_found = re.sub(r'<link rel="alternate"[^>]*>', "", not_found)
    not_found = re.sub(r'<meta[^>]*property="og:url"[^>]*>', "", not_found)
    not_found = re.sub(r'<meta[^>]*name="robots"[^>]*>', "", not_found, flags=re.I)
    not_found = not_found.replace("</head>", '<meta name="robots" content="noindex"/>\n</head>', 1)
    # The variant router would send phones to /m/404.html, which does not exist.
    not_found = not_found.replace(ROUTER_JS, "")
    open(os.path.join(OUT_DIR, "404.html"), "w", encoding="utf-8").write(not_found)

    log(f"\nassets: {stats['assets']} total — {stats['mirror']} from mirror, "
        f"{stats['cached']} from cache, {stats['downloaded']} downloaded, "
        f"{len(stats['failed'])} failed")
    if stats["downloaded"]:
        log(f"  note: {stats['downloaded']} asset(s) came from the live site and have been "
            f"archived into source/assets-cache/ — commit them.")
    else:
        log("  build was fully offline: nothing was fetched from the network.")
    for u in stats["failed"][:10]:
        log(f"  FAILED {u}")
    size = subprocess.run(["du", "-sh", OUT_DIR], capture_output=True, text=True).stdout.split()[0]
    log(f"output: {OUT_DIR}  ({size})")
    return outputs


if __name__ == "__main__":
    main()

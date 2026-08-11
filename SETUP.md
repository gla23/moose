# Gracious Moose Designs — static site

The old Wix site, converted to a static site for GitHub Pages. Six pages, no
JavaScript framework, no Wix runtime, no third-party requests at all.

## Layout

```
build.py         the converter — edit the CONFIG block at the top, then re-run
source/          archived input. The build reads only from here — see below
docs/            the built site. What GitHub Pages serves. Generated: don't hand-edit
licenses/        OFL licence texts for every font in source/gf/
LICENSE.md       copyright: all rights reserved, with the OFL fonts carved out
SETUP.md         this file — build, deploy, configure
FONTS.md         which fonts were removed, why, and what replaced them
EMAIL.md         how iCloud+ custom domains work, the DNS setup, and what to do after
```

## Source material — the Wix site is no longer needed

**The build does not touch the network.** Everything it reads is committed under
`source/`, so the site can be rebuilt after the Wix original is taken down:

```
source/orig/           6 desktop pages, as Wix served them        (2.7 MB)
source/orig-mobile/    6 mobile pages — a separate Wix render     (3.2 MB)
source/raw/            the wget mirror: images and page requisites (21 MB)
source/assets-cache/   115 assets the mirror lacked (mobile crops) (6.8 MB)
source/gf/             OFL fonts — the whole font-review pool      (744 KB)
```

Asset resolution order is **mirror → cache → network**, and anything that ever does
come off the network is written into `source/assets-cache/` so the next build is
offline again. The build prints which path each asset came from and says
`build was fully offline` when nothing was fetched. If it ever reports downloads,
commit the new cache files.

Verified by running the build with all network proxied to a dead port: 337 assets,
0 downloaded, 0 failed.

> **`source/raw/` deliberately contains no font binaries.** The wget mirror
> originally held 66 of them — including Helvetica, Avenir LT, DIN Next, Wix
> Madefor, Moon Flower and Allenattore, none redistributable. They were excluded
> when archiving, and `.gitignore` blocks them from returning if the mirror is
> re-taken. `build.py` ignores font URLs anyway, so nothing is lost.

`source/gf/` holds all 26 faces from the font comparison, not just the 7 deployed,
so a pairing can be changed without re-downloading. `licenses/` carries an OFL text
for all 20 families; the build copies only the ones for fonts it actually ships.

## Desktop and mobile

Wix served a **completely separate mobile page** — its own layout, its own
`viewport width=320`, its own image crops — chosen server-side from the
User-Agent. GitHub Pages can't do that, so both renders are built:

```
docs/          desktop  (viewport width=device-width, 980px layout)
docs/m/        mobile   (viewport width=320, device-mobile-optimized)
```

A short script in `<head>` picks between them on first paint. It keys off
`screen.width`, **not** the viewport, because the two variants declare different
viewport metas — deciding from the viewport would be self-confirming and could
ping-pong. Phones (shortest screen edge ≤ 500px) get `/m/`; tablets and desktops
get the desktop render, matching what Wix itself did.

For search engines the pair uses the standard separate-URL pattern: every mobile
page canonicalises to its desktop twin, and each desktop page declares a
`rel="alternate"` pointing at the mobile one, so the two aren't read as duplicates.

## Building

```bash
python3 build.py
```

`docs/` is deleted and rebuilt from scratch each run, entirely from `source/`.

### How the mirror was taken

For reference, in case it ever needs re-taking. `pages-sitemap.xml` gives the exact
page list, so recursion is unnecessary — feeding the six URLs in directly keeps
wget out of Wix's `/_api/` paths and off the wix.com marketing site:

```bash
wget \
  --input-file=pages.txt \
  --page-requisites \
  --adjust-extension \
  --convert-links \
  --span-hosts \
  --domains=amarissandersen.wixsite.com,static.wixstatic.com,static.parastorage.com,siteassets.parastorage.com,video.wixstatic.com \
  --execute robots=off \
  --user-agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36' \
  --restrict-file-names=windows \
  --timeout=30 --tries=3 --waitretry=2 --retry-connrefused
```

`--span-hosts` with an explicit `--domains` allowlist is required, as assets live on
two CDNs. `--restrict-file-names=windows` matters because Wix media URLs are full of
commas and query strings. A real browser User-Agent matters because Wix serves a
degraded page to unknown agents.

Two flags to avoid: `--mirror` implies `-N` (timestamping), which warns and
misbehaves alongside `-E`/`-k`; and `--no-parent` becomes a trap once `-H` is on,
because it can reject CDN assets sitting outside the start URL's directory.

Re-run the same command with an iPhone User-Agent to get the mobile render.

## Previewing

The pages use root-relative paths (`/assets/…`, `/about/`), so opening
`docs/index.html` directly with `file://` will not load images or fonts. Serve it:

```bash
cd docs && python3 -m http.server 8000
# then open http://localhost:8000
```

## Deploying

Repo **Settings → Pages → Source: Deploy from a branch**, branch **`master`**
(this repo uses `master`, not `main`), folder **`/docs`**. No Actions workflow
needed. `.nojekyll` is generated inside `docs/` so Jekyll doesn't touch the output.

### If Pages shows a plain page reading "Gracious Moose site"

That's Jekyll rendering the root `README.md`, which means the folder is set to
**`/ (root)`** rather than `/docs`. The repo root has no `index.html`, so Jekyll
falls back to building the README into a themed page — the repo name appears as the
site title and the README heading as the body.

The fix is only the folder setting; nothing in the build needs changing. Note that
adding a `.nojekyll` at the repo root would *not* help — it would stop Jekyll
building the README and leave you with a 404 instead, because the root genuinely
has no site in it.

## Configuration

Everything you'd want to change is in the `CONFIG` block at the top of `build.py`:

| Setting | What it does |
|---|---|
| `SITE_DOMAIN` | Your domain, once bought. Writes `CNAME`, `sitemap.xml`, and the `canonical`/`og:url` tags. Leave `""` to deploy on `github.io` — those tags are simply omitted rather than pointing somewhere wrong. |
| `CONTACT_EMAIL` | Address the two forms send to. Set to `hello@graciousmoosedesigns.com`. Setting it back to `""` makes the forms inert again, with a `TODO` in the markup, rather than pointing at a dead address. |
| `FONT_HEADING` | Face for "Gracious" and all six section headings. |
| `FONT_WORDMARK` | Face for the "Moose" half of the wordmark only. |
| `FONT_BODY` / `FONT_SERIF` | Body sans (replaces Avenir) and the kept serif. |
| `TEXT_FIXES` | Text-node-only string fixes. Applied to text nodes only, never attributes — a blind replace corrupts the Etsy shop URL. |

### The domain: graciousmoosedesigns.com

`SITE_DOMAIN` is set, so the build already writes `docs/CNAME`, `sitemap.xml`,
`robots.txt` with the sitemap line, and the `canonical`/`og:url` tags. What's left
is DNS and the repo setting.

**1. DNS records** — apex to GitHub Pages' four addresses, plus `www`:

| Type | Name | Value |
|---|---|---|
| A | `@` | `185.199.108.153` |
| A | `@` | `185.199.109.153` |
| A | `@` | `185.199.110.153` |
| A | `@` | `185.199.111.153` |
| CNAME | `www` | `<user>.github.io` |

All four A records — they're redundant servers, not alternatives.

**2. On Cloudflare, set these to DNS only (grey cloud).** Proxied, GitHub can't
complete its certificate challenge and HTTPS never provisions. This is separate
from the mail records in `EMAIL.md`, which coexist fine: MX governs mail, A/CNAME
govern web traffic.

**3. Repo Settings → Pages → Custom domain** → `graciousmoosedesigns.com` → then
tick **Enforce HTTPS** once the certificate is issued (usually minutes, sometimes
an hour).

`.com` is sold by Cloudflare Registrar, so the domain and its DNS can both live
there if you want them in one place.

### Changing the domain

Edit `SITE_DOMAIN` in `build.py`, re-run, commit. Setting it to `""` cleanly omits
the canonical/og tags and `CNAME` rather than pointing them somewhere wrong.

## What the conversion does

- **Strips every `<script>`.** All CSS is inline in the page (~263 KB across 17
  `<style>` blocks) and every `<img>` carries a real `src`, so the pages render
  fully without JavaScript. Removing the scripts also removes the `accessToken`,
  `svSession` and `metaSiteId` values Wix embedded, and the Sentry DSNs.
- **Removes the Wix branding**: the `#WIX_ADS` freemium banner, the
  `generator` meta tag, the `wix.com` favicon links, and the resource hints
  pointing at Wix CDNs. Remaining `wix.com` anchors become inert `<span>`s.
- **Localises every asset.** 337 images and fonts are rewritten to `/assets/…`.
  Nothing is fetched from `wixstatic.com` or `parastorage.com` at runtime.
- **Substitutes the fonts** that cannot legally be redistributed — see `FONTS.md`.
- **Fixes the capitalisation** of `EXPlore DESIGNS` and the run-together
  `GraciousMooseDesigns` in the footer.
- **Keeps the copyright year current** via a `<span data-current-year>` and three
  lines of JavaScript, so it no longer says 2020.
- Adds `.nojekyll`, `robots.txt`, a `404.html`, and `sitemap.xml` (once a domain is set).

### Repainting what the Wix runtime used to do

Four things looked broken once the JavaScript went, all found by screenshotting the
build against the live site. Each is fixed in `build.py`:

| Symptom | Cause | Fix |
|---|---|---|
| Nav collapsed to "HomeAboutExplore DesignsGet in touchMore" | Wix's JS wrote `width:245px` inline on each item (its intent is recorded in `data-same-width-buttons`), and hid the "More" overflow bucket | equal-width flex + hide "More" |
| "Explore Designs" dropdown never opened, orphaning `/notecards-stationery/` | Wix cloned the items into a JS-built panel; the `<ul>` in the markup is an aria-hidden fallback with an **inline** `display:none` | strip the inline style at build time, then style the fallback as the dropdown |
| Dropdown still invisible after that | the menu box computes `overflow: hidden auto`, clipping it to the 37px strip so it never painted | `overflow: visible` on `wix-dropdown-menu` |
| Page background blurry | Wix ships a 253×288 `blur_2` placeholder as the SSR `src` and swaps in the real image on hydration | rebuild the URL from the sibling `data-image-info` |
| Mobile: raw blue links spilling over the header | `#TINY_MENU` carries an SEO-only link list Wix kept hidden while driving its overlay | hide it, and reuse it as the dropdown the hamburger opens |
| "Featured designs" carousel inert — arrows and thumbnails did nothing | Wix rendered only the first two slides and fetched the rest on demand; its runtime drove the arrows | derive every slide from the thumbnail strip and drive it from the shim |

Two notes for anyone editing that CSS. Hiding "More" needs `!important`, which isn't
laziness: Wix's own rule is a four-class selector (`.SiBgBF .Kefle8 .iTBB8q
.QBNfeJ`) and outranks anything we can write without depending on hashed class
names that change if the site is re-mirrored. And the selectors deliberately key off
stable hooks — `data-testid`, `wixui-*` classes, `data-*` attributes — for the same
reason.

Geometry now matches the live site exactly: four nav items at x=230/475/720/965,
245px each; dropdown 245×94 on `#dbdbdb` with 47px rows.

### The carousel

The thumbnail strip is the only place every item appears — Wix rendered just two
full-size slides. A thumbnail URL differs from its slide only in the transform
(`w_120,h_120,q_70` against the slide's `w_696,h_402,q_90`), so `wire_gallery()`
derives a 1× and 2× slide URL per thumbnail and writes both lists onto the gallery
as `data-gm-slides` / `data-gm-slides-2x`. The shim then drives the existing "next"
arrow, synthesises the "prev" arrow Wix only rendered once you were past slide one,
and makes the thumbnails selectable. Desktop gets 7 slides, mobile 5 — the mobile
render lazily emitted fewer thumbnails.

Two traps worth knowing if you touch this:

- The slide `<img>` lives inside a `<picture>`, so its `<source srcset>` beats any
  `src` you set. Setting `img.src` changed the attribute and nothing else. The shim
  removes the sources and drives `img.srcset` instead, keeping a 2× entry so retina
  screens stay sharp.
- `URL_RE` must exclude `|`. The slide lists are pipe-separated, and without that
  exclusion one match runs straight through the separators and localises all seven
  URLs as a single bogus asset.

### The contact form

Reduced to Name / Email / Message via `FORM_DROP` / `FORM_KEEP` in `build.py`. The
grid rows are `min-content`, so deleting a field collapses its row with no gap, and
the two survivors are widened to whatever width the message field declares — read
from the page, because desktop (510px) and mobile differ. Wrapper elements are
found from the input `name` via Wix's own `input_<wrapperId>` convention rather than
hardcoded hashes.

### The JavaScript shim

Two small inline scripts per page, in place of Wix's ~2 MB React runtime:

- **The variant router** (in `<head>`, so it runs before layout) — see above.
- **The shim** (before `</body>`) — keeps the copyright year current, toggles the
  mobile hamburger menu, and reveals containers Wix marked `visibility:hidden`
  until hydration.

## Verification

`build.py` output is checked on each run: every asset reference resolves to a real
file, every internal link across both variants resolves, and no page contains
`wixsite.com`, `wixstatic.com`, `parastorage.com`, `wix.com`, `accessToken`,
`svSession`, `metaSiteId` or the Wix generator tag. The only external hosts any page
requests are `etsy.com` and `instagram.com`.

The wordmark override reports a count per page (expected: 1 each), so if Wix's
markup ever changes shape, a rebuild says so rather than silently producing the
wrong font.

### Checking it in a real browser

`scripts/` drives the shared Playwright browser server (see the notes in
`/Users/gandersen/dev/gla/tab/scripts/browser.ts`, which they import):

```bash
node --experimental-strip-types ./scripts/shots.ts    # all 12 pages + problem report
node --experimental-strip-types ./scripts/verify.ts   # nav geometry, dropdown, background
node --experimental-strip-types ./scripts/mobile.ts   # hamburger open/close
```

`node`, not `bun` — bun answers WebSockets from its own networking and the tunnel
never applies.

These do **not** need a web server, which matters because this sandbox can't bind a
listening socket at all — `bind()` is denied on every host and port, so
`python3 -m http.server` and `npx serve` both fail. Instead `page.route` fulfils
every request from `docs/` on disk, which gives the same result as a static server
rooted there. `shots.ts` reports 404s, console errors, broken images, horizontal
overflow, and how many font faces loaded; a clean run prints `0 problem(s)`.

Last run: 12 pages, 0 problems, and the phone-viewport router correctly landing
on `/m/`.

## Known limitations

- **The two forms open the visitor's mail client** rather than posting anywhere.
  Wix handled submissions server-side and there's no backend now, so the shim
  intercepts submit and builds a pre-filled message to `CONTACT_EMAIL`. The contact
  form becomes "Website enquiry from <name>" with the fields as labelled lines and
  the message below; the newsletter form becomes "Mailing list signup".

  Two consequences worth knowing. A visitor with no configured mail client sees
  nothing happen — a hosted form service is the fix if that matters. And because
  it's the visitor's own mail app, you get their real address in the From header,
  which makes replying straightforward.

  Note the `action="mailto:…"` attribute on the form is a no-JS fallback only; the
  JS path is what normally runs, because a bare `mailto:` form POST is unreliable
  (Chrome largely ignores it).
- **The homepage carousel works; the lightbox does not.** Arrows and thumbnails
  navigate, but clicking a slide no longer opens Wix's full-screen viewer. The grid
  galleries on the other pages render every item and are unaffected.
- **The mobile grid galleries show fewer items than desktop.** Wix's mobile render
  emitted 5 items against desktop's 18 on `/explore-designs/` and
  `/notecards-stationery/`, and lazily fetched the rest. Worth addressing if mobile
  visitors should see the full range — it would mean generating the missing items
  the way `wire_gallery()` does for the carousel.
- **The mobile menu needs JavaScript.** The dropdown it opens is CSS, but the
  toggle is in the shim. The desktop nav and its dropdown are pure CSS and work
  without it.
- **The tall white gap above the footer on the homepage is original.** Live body
  height was 2561px against our 2512px — a 49px difference that is exactly the
  removed Wix banner, so the layout matches rather than having collapsed.
- **`docs/` is 27 MB** across 13 pages and 348 assets, mostly because Wix generated
  many resized variants of each image for `srcSet`, and desktop and mobile use
  different crops. Well within the Pages 1 GB limit, but a future cleanup could
  prune unused variants.
- **The variant router needs JavaScript.** With JS disabled, everyone gets the
  desktop render — degraded on a phone, but readable, and every link still works.

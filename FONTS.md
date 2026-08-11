# Fonts

The Wix site loaded seven typefaces. Only one of them could legally be committed to
a public repository, so the rest were substituted. This file is the record of that.

## What was removed, and why

| Font | Set | Why it couldn't ship |
|---|---|---|
| **Moon Flower** (Denise Bentulan) | "Moose" + 6 headings | Font's own name table: *"Free for personal use. For commercial use, contact the designer"* |
| **Allenattore** (Kotak Kuning Studio) | "Gracious" | ©2018 commercial foundry release |
| **Avenir LT** W01/W05 | most running text | Monotype — licensed to Wix's CDN, not to us |
| **Helvetica** W01/W02/LT W10 | UI text | Monotype — licensed to Wix |
| **Wix Madefor** | UI text | Wix's proprietary corporate typeface |
| **DIN Next** W01/W02/W10 | Wix banner only | Monotype — removed along with the banner |

Both custom faces were uploaded to Wix by the site owner (they were served from
`static.wixstatic.com/ufonts/…`). Uploading a font for use on your own site is not
the same as a licence to redistribute the file, which is what committing it to a
public repo would do — so neither is in this repository.

> **Worth knowing:** Moon Flower's licence restricts it to *personal* use. The site
> links to an Etsy shop, which makes its use there arguably commercial. That
> predates this migration and is unaffected by it, but if you want the original
> lettering back, contacting Denise Bentulan for a commercial licence is the route.

## What ships instead

All four are SIL Open Font License 1.1, self-hosted from `docs/assets/fonts/`,
with their licence texts alongside them as the OFL requires.

| Role | Font | Replaces |
|---|---|---|
| Wordmark — "Gracious" | **Shadows Into Light** | Allenattore |
| Wordmark — "Moose" | **Grand Hotel** | Moon Flower |
| Section headings | **Shadows Into Light** | Moon Flower |
| Body text | **Mulish** (300/400/600) | Avenir LT |
| Body serif | **Libre Baskerville** (400/700) | *kept — it was already OFL* |
| UI text | system stack | Helvetica, Wix Madefor |

Libre Baskerville was the one font already in use that we could keep: Wix was
serving it from a Google Fonts cache. It's now self-hosted from the OFL release.

## How the substitution works

Wix's inline CSS contains thousands of `font-family` declarations referencing
generated names like `wfont_1532cc_c96f6f5c049f4561909346e2169a81ed` and
`avenir-lt-w01_35-light1475496`. Rather than rewrite them all, `build.py`:

1. Deletes every `@font-face` block pointing at a Wix font URL.
2. Re-declares those **same family names** with `src` pointing at our OFL files.

So the existing declarations keep resolving and nothing else has to change. The
`Avenir` names encode weight (`_35-light`, `_85-heavy`), which are mapped onto
Mulish 300 and 600.

The one exception is the wordmark. "Gracious" and "Moose" were both Moon Flower but
now need different faces, and the element carrying `font-family` is an *ancestor* of
the text — the word itself sits in a nested `<a>`. So `override_wordmark()` finds
spans styled with the Moon Flower stack, checks that the next visible text is
"Moose", and re-points just those. It reports a count per page at build time
(expected: 1 each) so a markup change upstream can't silently break it.

## Changing the pairing

Edit `FONT_HEADING` / `FONT_WORDMARK` in `build.py` and re-run. Any Google Fonts
`woff2` dropped into the font directory works; add its `OFL.txt` to `licenses/`.

## Capitalisation

`EXPlore DESIGNS` was written that way to coax particular decorative glyphs out of
Moon Flower. With a conventional face it just reads as a typo, so `TEXT_FIXES` in
`build.py` normalises it to `Explore Designs`, and the footer's `GraciousMooseDesigns`
to `Gracious Moose Designs`.

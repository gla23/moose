/// <reference types="node" />
import fs from 'node:fs';
import path from 'node:path';
import { withPage } from '/Users/gandersen/dev/gla/tab/scripts/browser.ts';

/**
 * Screenshot the built site and report render problems.
 *
 * The sandbox can't bind a listening socket, so there's no local server to point the
 * (out-of-sandbox) browser at. Instead every request is fulfilled by Playwright from
 * docs/ on disk, which this process can read. Same effect as a static server, minus
 * the socket.
 *
 *   node --experimental-strip-types ./scripts/shots.ts
 */

const ROOT = '/Users/gandersen/dev/moose/docs';
const OUT = '/tmp/claude/shots';
const ORIGIN = 'http://moose.test';

const MIME: Record<string, string> = {
	'.html': 'text/html; charset=utf-8',
	'.css': 'text/css',
	'.js': 'text/javascript',
	'.json': 'application/json',
	'.png': 'image/png',
	'.jpg': 'image/jpeg',
	'.jpeg': 'image/jpeg',
	'.gif': 'image/gif',
	'.svg': 'image/svg+xml',
	'.webp': 'image/webp',
	'.avif': 'image/avif',
	'.ico': 'image/x-icon',
	'.woff': 'font/woff',
	'.woff2': 'font/woff2',
	'.ttf': 'font/ttf',
	'.txt': 'text/plain',
	'.xml': 'application/xml',
};

const PAGES = ['/', '/about/', '/explore-designs/', '/notecards-stationery/', '/christmas/', '/get-in-touch/'];

function resolveFile(urlPath: string): string | null {
	let p = decodeURIComponent(urlPath.split('?')[0]);
	if (p.endsWith('/')) p += 'index.html';
	const full = path.normalize(path.join(ROOT, p));
	if (!full.startsWith(ROOT)) return null;
	try {
		return fs.statSync(full).isFile() ? full : null;
	} catch {
		return null;
	}
}

type Problem = { page: string; kind: string; detail: string };
const problems: Problem[] = [];

await withPage(async (page) => {
	fs.mkdirSync(OUT, { recursive: true });

	let current = '';
	const external = new Set<string>();

	await page.route('**/*', async (route) => {
		const url = new URL(route.request().url());
		if (url.origin !== ORIGIN) {
			external.add(url.origin);
			// Third-party (etsy/instagram) are links, not subresources — never needed to render.
			return route.abort();
		}
		const file = resolveFile(url.pathname);
		if (!file) {
			problems.push({ page: current, kind: '404', detail: url.pathname });
			return route.fulfill({ status: 404, contentType: 'text/plain', body: 'not found' });
		}
		return route.fulfill({
			status: 200,
			contentType: MIME[path.extname(file).toLowerCase()] ?? 'application/octet-stream',
			body: fs.readFileSync(file),
		});
	});

	page.on('console', (m) => {
		if (m.type() === 'error') problems.push({ page: current, kind: 'console', detail: m.text().slice(0, 200) });
	});
	page.on('pageerror', (e) => problems.push({ page: current, kind: 'pageerror', detail: String(e).slice(0, 200) }));

	async function shoot(label: string, url: string, width: number, height: number) {
		current = label;
		await page.setViewportSize({ width, height });
		await page.goto(ORIGIN + url, { waitUntil: 'networkidle' });
		await page.waitForTimeout(700);

		const report = await page.evaluate(() => {
			const fam = (sel: string) => {
				const el = document.querySelector(sel);
				return el ? getComputedStyle(el).fontFamily : null;
			};
			// horizontal overflow: anything sticking out past the document width
			const de = document.documentElement;
			const overflowers: string[] = [];
			document.querySelectorAll('*').forEach((el) => {
				const r = (el as HTMLElement).getBoundingClientRect();
				if (r.width > 0 && (r.right > de.clientWidth + 4 || r.left < -4)) {
					const t = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '');
					if (overflowers.length < 12 && !overflowers.includes(t)) overflowers.push(t);
				}
			});
			const imgs = Array.from(document.images);
			return {
				title: document.title,
				url: location.pathname,
				scrollW: de.scrollWidth,
				clientW: de.clientWidth,
				bodyH: document.body.scrollHeight,
				fontsReady: document.fonts.status,
				// Count faces the browser actually loaded. Don't test by our own family
				// names: the page references Wix's generated tokens (wfont_…, avenir-lt-…)
				// which we re-point at the substitute files, so document.fonts.check("Mulish")
				// is false even when Mulish is loaded and rendering.
				loadedFaces: (() => {
					const names: string[] = [];
					document.fonts.forEach((f) => { if (f.status === 'loaded') names.push(f.family); });
					return names;
				})(),
				brokenImgs: imgs.filter((i) => i.complete && i.naturalWidth === 0).map((i) => i.currentSrc || i.src).slice(0, 8),
				imgCount: imgs.length,
				headerFont: fam('#SITE_HEADER h1, #SITE_HEADER span, header span'),
				overflowers,
				visibleText: (document.body.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 160),
			};
		});

		const file = path.join(OUT, label + '.png');
		await page.screenshot({ path: file, fullPage: true });

		if (report.scrollW > report.clientW + 4)
			problems.push({ page: label, kind: 'h-overflow', detail: `scrollW ${report.scrollW} > clientW ${report.clientW} — ${report.overflowers.join(', ')}` });
		if (report.brokenImgs.length)
			problems.push({ page: label, kind: 'broken-img', detail: report.brokenImgs.join(' | ') });
		if (report.loadedFaces.length < 6)
			problems.push({ page: label, kind: 'font', detail: `only ${report.loadedFaces.length} faces loaded` });

		console.log(`\n### ${label}  ->  ${path.basename(file)}`);
		console.log(`   url=${report.url} title=${report.title.slice(0, 50)}`);
		console.log(`   page ${report.scrollW}x${report.bodyH} (viewport ${width})  imgs=${report.imgCount} broken=${report.brokenImgs.length}`);
		console.log(`   fonts=${report.fontsReady} facesLoaded=${report.loadedFaces.length}`);
		if (report.overflowers.length) console.log(`   overflow: ${report.overflowers.join(', ')}`);
		console.log(`   text: ${report.visibleText.slice(0, 120)}`);
	}

	// desktop
	for (const p of PAGES) {
		const name = 'desktop' + (p === '/' ? '-home' : p.replace(/\//g, '-').replace(/-$/, ''));
		await shoot(name, p, 1440, 900);
	}
	// mobile variants, at a phone viewport
	for (const p of PAGES) {
		const name = 'mobile' + (p === '/' ? '-home' : p.replace(/\//g, '-').replace(/-$/, ''));
		await shoot(name, '/m' + p, 390, 844);
	}

	// does the router send a phone from / to /m/ ?
	current = 'router';
	await page.setViewportSize({ width: 390, height: 844 });
	await page.goto(ORIGIN + '/', { waitUntil: 'networkidle' });
	await page.waitForTimeout(900);
	console.log(`\n### router check: phone viewport landed on ${new URL(page.url()).pathname}`);

	console.log(`\n=== external origins blocked: ${[...external].join(', ') || 'none'} ===`);
});

console.log(`\n=== ${problems.length} problem(s) ===`);
for (const p of problems) console.log(`  [${p.kind}] ${p.page}: ${p.detail}`);

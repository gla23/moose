/// <reference types="node" />
import fs from 'node:fs';
import path from 'node:path';
import { withPage } from '/Users/gandersen/dev/gla/tab/scripts/browser.ts';

const ROOT = '/Users/gandersen/dev/moose/docs';
const ORIGIN = 'http://moose.test';
const OUT = '/tmp/claude/verify';
const MIME: Record<string, string> = {
	'.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript',
	'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
	'.svg': 'image/svg+xml', '.webp': 'image/webp', '.avif': 'image/avif',
	'.woff2': 'font/woff2', '.woff': 'font/woff', '.txt': 'text/plain', '.xml': 'application/xml',
};
function resolveFile(u: string): string | null {
	let p = decodeURIComponent(u.split('?')[0]);
	if (p.endsWith('/')) p += 'index.html';
	const f = path.normalize(path.join(ROOT, p));
	if (!f.startsWith(ROOT)) return null;
	try { return fs.statSync(f).isFile() ? f : null; } catch { return null; }
}

fs.mkdirSync(OUT, { recursive: true });

await withPage(async (page) => {
	await page.route('**/*', async (route) => {
		const url = new URL(route.request().url());
		if (url.origin !== ORIGIN) return route.abort();
		const f = resolveFile(url.pathname);
		if (!f) return route.fulfill({ status: 404, body: 'nf' });
		return route.fulfill({ status: 200, contentType: MIME[path.extname(f).toLowerCase()] ?? 'application/octet-stream', body: fs.readFileSync(f) });
	});

	await page.setViewportSize({ width: 1440, height: 900 });
	await page.goto(ORIGIN + '/', { waitUntil: 'networkidle' });
	await page.waitForTimeout(900);

	const nav = await page.evaluate(() => {
		const items = Array.from(document.querySelectorAll('#comp-j7a3ujy8 > nav > ul > li')).map((li) => {
			const r = li.getBoundingClientRect();
			return {
				text: (li.textContent || '').trim().slice(0, 22),
				x: Math.round(r.x), w: Math.round(r.width),
				display: getComputedStyle(li).display,
			};
		});
		const bg = document.querySelector('[id^="img_pageBackground"] img, wow-image[id^="img_pageBackground"] img') as HTMLImageElement | null;
		return {
			items,
			bg: bg ? { nat: bg.naturalWidth + 'x' + bg.naturalHeight, rendered: Math.round(bg.getBoundingClientRect().width) + 'x' + Math.round(bg.getBoundingClientRect().height) } : null,
			scrollW: document.documentElement.scrollWidth,
			clientW: document.documentElement.clientWidth,
		};
	});
	console.log('=== nav items (live target: 4 x 245px starting at x=230) ===');
	nav.items.forEach((i) => console.log(`   "${i.text}" x=${i.x} w=${i.w} display=${i.display}`));
	console.log('=== page background ===', JSON.stringify(nav.bg));
	console.log(`=== overflow: scrollW=${nav.scrollW} clientW=${nav.clientW} ===`);

	await page.screenshot({ path: path.join(OUT, 'header.png'), clip: { x: 0, y: 0, width: 1440, height: 420 } });

	// hover the submenu parent
	const li = page.locator('#comp-j7a3ujy8 > nav > ul > li').filter({ hasText: 'Explore Designs' }).first();
	await li.hover();
	await page.waitForTimeout(600);
	const sub = await page.evaluate(() => {
		const li = Array.from(document.querySelectorAll('#comp-j7a3ujy8 > nav > ul > li')).find((l) => l.querySelector('ul'))!;
		const ul = li.querySelector('ul')!;
		const cs = getComputedStyle(ul);
		const r = ul.getBoundingClientRect();
		const links = Array.from(ul.querySelectorAll('a')).map((a) => {
			const ar = a.getBoundingClientRect();
			const acs = getComputedStyle(a);
			return { t: (a.textContent || '').trim().slice(0, 24), w: Math.round(ar.width), h: Math.round(ar.height), font: acs.fontFamily.split(',')[0], size: acs.fontSize, color: acs.color };
		});
		return { display: cs.display, bg: cs.backgroundColor, rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)], links };
	});
	console.log('\n=== submenu on hover (live target: 245x94, bg rgb(219,219,219), 47px items) ===');
	console.log('  ', JSON.stringify(sub, null, 1));
	await page.screenshot({ path: path.join(OUT, 'submenu.png'), clip: { x: 200, y: 200, width: 1040, height: 260 } });

	// mobile
	await page.setViewportSize({ width: 390, height: 844 });
	await page.goto(ORIGIN + '/m/', { waitUntil: 'networkidle' });
	await page.waitForTimeout(800);
	await page.screenshot({ path: path.join(OUT, 'mobile-top.png'), clip: { x: 0, y: 0, width: 390, height: 700 } });
	const mob = await page.evaluate(() => ({
		scrollW: document.documentElement.scrollWidth,
		clientW: document.documentElement.clientWidth,
		hasDropdownMenu: !!document.querySelector('wix-dropdown-menu'),
	}));
	console.log('\n=== mobile ===', JSON.stringify(mob));
});

/// <reference types="node" />
import fs from 'node:fs';
import path from 'node:path';
import { withPage } from '/Users/gandersen/dev/gla/tab/scripts/browser.ts';

const ROOT = '/Users/gandersen/dev/moose/docs';
const ORIGIN = 'http://moose.test';
const OUT = '/tmp/claude/verify';
const MIME: Record<string, string> = {
	'.html': 'text/html; charset=utf-8', '.css': 'text/css', '.png': 'image/png',
	'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml',
	'.webp': 'image/webp', '.avif': 'image/avif', '.woff2': 'font/woff2',
};
function resolveFile(u: string): string | null {
	let p = decodeURIComponent(u.split('?')[0]);
	if (p.endsWith('/')) p += 'index.html';
	const f = path.normalize(path.join(ROOT, p));
	if (!f.startsWith(ROOT)) return null;
	try { return fs.statSync(f).isFile() ? f : null; } catch { return null; }
}

const state = () =>
	({
		src: (document.querySelector('[data-gm-slides] img') as HTMLImageElement).currentSrc.split('/').pop(),
		selected: Array.from(document.querySelectorAll('[data-gm-slides] .thumbnailItem'))
			.findIndex((t) => t.classList.contains('pro-gallery-highlight')),
		arrows: Array.from(document.querySelectorAll('[data-gm-slides] button[data-hook^="nav-arrow"]'))
			.map((b) => b.getAttribute('data-hook')),
		naturalW: (document.querySelector('[data-gm-slides] img') as HTMLImageElement).naturalWidth,
	});

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
	await page.evaluate(() => document.querySelector('[data-gm-slides]')!.scrollIntoView({ block: 'center' }));
	await page.waitForTimeout(300);

	console.log('initial      ', JSON.stringify(await page.evaluate(state)));

	for (let i = 1; i <= 3; i++) {
		await page.click('[data-gm-slides] button[data-hook="nav-arrow-next"]');
		await page.waitForTimeout(350);
		console.log(`after next x${i}`, JSON.stringify(await page.evaluate(state)));
	}
	await page.click('[data-gm-slides] button[data-hook="nav-arrow-prev"]');
	await page.waitForTimeout(350);
	console.log('after prev   ', JSON.stringify(await page.evaluate(state)));

	// click the 6th thumbnail
	await page.evaluate(() => (document.querySelectorAll('[data-gm-slides] .thumbnailItem')[5] as HTMLElement).click());
	await page.waitForTimeout(400);
	console.log('thumb #6     ', JSON.stringify(await page.evaluate(state)));

	const r = await page.evaluate(() => {
		const g = document.querySelector('[data-gm-slides]')!.getBoundingClientRect();
		return [Math.round(g.x), Math.round(g.y), Math.round(g.width), Math.round(g.height)];
	});
	await page.screenshot({ path: path.join(OUT, 'carousel.png'), clip: { x: r[0] - 40, y: r[1] - 10, width: r[2] + 80, height: r[3] + 20 } });

	// wrap-around from the last slide
	for (let i = 0; i < 2; i++) {
		await page.click('[data-gm-slides] button[data-hook="nav-arrow-next"]');
		await page.waitForTimeout(300);
	}
	console.log('wrapped      ', JSON.stringify(await page.evaluate(state)));
});

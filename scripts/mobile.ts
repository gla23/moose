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

await withPage(async (page) => {
	await page.route('**/*', async (route) => {
		const url = new URL(route.request().url());
		if (url.origin !== ORIGIN) return route.abort();
		const f = resolveFile(url.pathname);
		if (!f) return route.fulfill({ status: 404, body: 'nf' });
		return route.fulfill({ status: 200, contentType: MIME[path.extname(f).toLowerCase()] ?? 'application/octet-stream', body: fs.readFileSync(f) });
	});
	await page.setViewportSize({ width: 390, height: 844 });
	await page.goto(ORIGIN + '/m/', { waitUntil: 'networkidle' });
	await page.waitForTimeout(800);

	const closed = await page.evaluate(() => {
		const ul = document.querySelector('#TINY_MENU > ul') as HTMLElement;
		const btn = document.querySelector('[data-testid="tinymenu-menubutton"]') as HTMLElement;
		const br = btn.getBoundingClientRect();
		return {
			ulDisplay: getComputedStyle(ul).display,
			burger: [Math.round(br.x), Math.round(br.y), Math.round(br.width), Math.round(br.height)],
			ariaExpanded: btn.getAttribute('aria-expanded'),
			scrollW: document.documentElement.scrollWidth,
		};
	});
	console.log('closed:', JSON.stringify(closed));
	await page.screenshot({ path: path.join(OUT, 'm-closed.png'), clip: { x: 0, y: 0, width: 390, height: 300 } });

	await page.click('[data-testid="tinymenu-menubutton"]');
	await page.waitForTimeout(500);
	const open = await page.evaluate(() => {
		const ul = document.querySelector('#TINY_MENU > ul') as HTMLElement;
		const r = ul.getBoundingClientRect();
		const btn = document.querySelector('[data-testid="tinymenu-menubutton"]') as HTMLElement;
		return {
			ulDisplay: getComputedStyle(ul).display,
			rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
			ariaExpanded: btn.getAttribute('aria-expanded'),
			links: Array.from(ul.querySelectorAll('a')).map((a) => {
				const ar = a.getBoundingClientRect();
				return { t: (a.textContent || '').trim().slice(0, 24), h: Math.round(ar.height), visible: ar.height > 0 };
			}),
		};
	});
	console.log('open  :', JSON.stringify(open, null, 1));
	await page.screenshot({ path: path.join(OUT, 'm-open.png'), clip: { x: 0, y: 0, width: 390, height: 400 } });

	// close again by clicking outside
	await page.mouse.click(60, 600);
	await page.waitForTimeout(400);
	const reclosed = await page.evaluate(() => getComputedStyle(document.querySelector('#TINY_MENU > ul') as HTMLElement).display);
	console.log('after outside click:', reclosed);
});

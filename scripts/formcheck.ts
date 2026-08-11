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

const PROBE = () => {
	const form = document.querySelector('form')!;
	const fr = form.getBoundingClientRect();
	const grid = form.querySelector('[data-mesh-id$="gridContainer"]') as HTMLElement;
	return {
		formRect: [Math.round(fr.x), Math.round(fr.y), Math.round(fr.width), Math.round(fr.height)],
		rows: getComputedStyle(grid).gridTemplateRows,
		kids: Array.from(grid.children).map((c) => {
			const cs = getComputedStyle(c as HTMLElement);
			const r = c.getBoundingClientRect();
			const f = c.querySelector('input, textarea') as HTMLInputElement | null;
			return {
				area: cs.gridArea,
				rect: [Math.round(r.x - fr.x), Math.round(r.y - fr.y), Math.round(r.width), Math.round(r.height)],
				field: f ? (f.getAttribute('name') || f.tagName.toLowerCase()) : null,
				ph: f ? f.getAttribute('placeholder') : null,
				text: (c.textContent || '').trim().slice(0, 18),
			};
		}),
	};
};

await withPage(async (page) => {
	await page.route('**/*', async (route) => {
		const url = new URL(route.request().url());
		if (url.origin !== ORIGIN) return route.abort();
		const f = resolveFile(url.pathname);
		if (!f) return route.fulfill({ status: 404, body: 'nf' });
		return route.fulfill({ status: 200, contentType: MIME[path.extname(f).toLowerCase()] ?? 'application/octet-stream', body: fs.readFileSync(f) });
	});

	for (const [label, url, w, h] of [['desktop', '/get-in-touch/', 1440, 900], ['mobile', '/m/get-in-touch/', 390, 844]] as const) {
		await page.setViewportSize({ width: w, height: h });
		await page.goto(ORIGIN + url, { waitUntil: 'networkidle' });
		await page.waitForTimeout(700);
		const d = await page.evaluate(PROBE);
		console.log(`\n=== ${label} ===`);
		console.log('  grid rows:', d.rows);
		console.log('  form rect:', JSON.stringify(d.formRect));
		d.kids.forEach((k: any) =>
			console.log(`   ${String(k.area).padEnd(14)} x=${String(k.rect[0]).padStart(4)} y=${String(k.rect[1]).padStart(4)} ${String(k.rect[2]).padStart(4)}x${String(k.rect[3]).padStart(3)} ${String(k.field).padEnd(11)} ${String(k.ph).padEnd(24)} "${k.text}"`));
		const fr = d.formRect;
		await page.screenshot({
			path: path.join(OUT, `form-${label}.png`),
			clip: { x: Math.max(0, fr[0] - 10), y: Math.max(0, fr[1] - 10), width: Math.min(w, fr[2] + 20), height: Math.min(h * 2, fr[3] + 20) },
		});
	}
});

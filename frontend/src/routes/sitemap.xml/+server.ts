import type { RequestHandler } from './$types';
import { apiClient } from '$lib/api/api-client';
import { generateCityUrl } from '$lib/utils/utils';

const SITE = 'https://engagic.org';

// All 50 US states + DC
const STATE_CODES = [
	'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL',
	'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME',
	'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH',
	'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI',
	'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
];

function escapeXml(str: string): string {
	return str
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&apos;');
}

function urlEntry(loc: string, changefreq: string, priority: string, lastmod?: string): string {
	let entry = `  <url>\n    <loc>${escapeXml(loc)}</loc>\n    <changefreq>${changefreq}</changefreq>\n    <priority>${priority}</priority>`;
	if (lastmod) {
		entry += `\n    <lastmod>${lastmod}</lastmod>`;
	}
	entry += '\n  </url>';
	return entry;
}

export const GET: RequestHandler = async ({ setHeaders }) => {
	const today = new Date().toISOString().split('T')[0];

	// Fetch all cities from the coverage API
	let cities: Array<{ name: string; state: string }> = [];
	try {
		const coverage = await apiClient.getCityCoverage();
		if (coverage.success && coverage.cities) {
			cities = coverage.cities;
		}
	} catch {
		// If API fails, generate sitemap with static pages only
	}

	// Deduplicate states that actually have cities
	const activeStates = new Set<string>();
	for (const city of cities) {
		activeStates.add(city.state);
	}

	const urls: string[] = [];

	// Static pages
	urls.push(urlEntry(`${SITE}/`, 'daily', '1.0', today));
	urls.push(urlEntry(`${SITE}/about/general`, 'monthly', '0.5'));
	urls.push(urlEntry(`${SITE}/about/metrics`, 'weekly', '0.6'));
	urls.push(urlEntry(`${SITE}/about/community`, 'monthly', '0.4'));
	urls.push(urlEntry(`${SITE}/about/donate`, 'monthly', '0.4'));
	urls.push(urlEntry(`${SITE}/about/terms`, 'monthly', '0.3'));
	urls.push(urlEntry(`${SITE}/country`, 'daily', '0.7', today));
	urls.push(urlEntry(`${SITE}/committees`, 'daily', '0.7', today));
	urls.push(urlEntry(`${SITE}/council-members`, 'daily', '0.7', today));

	// State pages (only states with active cities)
	for (const state of STATE_CODES) {
		if (activeStates.has(state)) {
			urls.push(urlEntry(`${SITE}/state/${state}`, 'daily', '0.7', today));
			urls.push(urlEntry(`${SITE}/state/${state}/meetings`, 'daily', '0.6', today));
		}
	}

	// City pages
	for (const city of cities) {
		const cityUrl = generateCityUrl(city.name, city.state);
		urls.push(urlEntry(`${SITE}/${cityUrl}`, 'daily', '0.8', today));
		urls.push(urlEntry(`${SITE}/${cityUrl}/council`, 'weekly', '0.5'));
		urls.push(urlEntry(`${SITE}/${cityUrl}/committees`, 'weekly', '0.5'));
	}

	const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.join('\n')}
</urlset>`;

	setHeaders({
		'Content-Type': 'application/xml',
		'Cache-Control': 'public, max-age=3600'
	});

	return new Response(xml);
};

import type { RequestHandler } from './$types';
import type { StateMeeting, StateMatterSummary } from '$lib/api/types';
import { apiClient } from '$lib/api/api-client';
import { generateCityUrl, generateMeetingSlug } from '$lib/utils/utils';

const SITE = 'https://engagic.org';
const MEETINGS_PER_STATE = 500;
const MATTERS_PER_STATE = 500;

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

function meetingLastmod(meeting: StateMeeting): string | undefined {
	if (!meeting.date) return undefined;
	const d = new Date(meeting.date);
	if (isNaN(d.getTime())) return undefined;
	return d.toISOString().split('T')[0];
}

function matterLastmod(matter: StateMatterSummary): string | undefined {
	if (!matter.last_seen) return undefined;
	const d = new Date(matter.last_seen);
	if (isNaN(d.getTime())) return undefined;
	return d.toISOString().split('T')[0];
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

	// Fetch meetings and matters per active state in parallel
	const stateList = [...activeStates];
	const [meetingResults, matterResults] = await Promise.all([
		Promise.allSettled(
			stateList.map(state => apiClient.getStateMeetings(state, MEETINGS_PER_STATE))
		),
		Promise.allSettled(
			stateList.map(state => apiClient.getStateMatters(state, undefined, MATTERS_PER_STATE))
		)
	]);

	const allMeetings: StateMeeting[] = [];
	for (const result of meetingResults) {
		if (result.status === 'fulfilled' && result.value.success) {
			allMeetings.push(...result.value.meetings);
		}
	}

	const allMatters: StateMatterSummary[] = [];
	for (const result of matterResults) {
		if (result.status === 'fulfilled' && result.value.success) {
			allMatters.push(...result.value.matters);
		}
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

	// State pages
	for (const state of stateList) {
		urls.push(urlEntry(`${SITE}/state/${state}`, 'daily', '0.7', today));
		urls.push(urlEntry(`${SITE}/state/${state}/meetings`, 'daily', '0.6', today));
	}

	// City pages
	for (const city of cities) {
		const cityUrl = generateCityUrl(city.name, city.state);
		urls.push(urlEntry(`${SITE}/${cityUrl}`, 'daily', '0.8', today));
		urls.push(urlEntry(`${SITE}/${cityUrl}/council`, 'weekly', '0.5'));
		urls.push(urlEntry(`${SITE}/${cityUrl}/committees`, 'weekly', '0.5'));
	}

	// Meeting pages
	for (const meeting of allMeetings) {
		const cityUrl = meeting.city_banana;
		const slug = generateMeetingSlug(meeting);
		urls.push(urlEntry(`${SITE}/${cityUrl}/${slug}`, 'weekly', '0.8', meetingLastmod(meeting)));
	}

	// Matter pages
	for (const matter of allMatters) {
		urls.push(urlEntry(`${SITE}/matter/${matter.id}`, 'weekly', '0.7', matterLastmod(matter)));
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

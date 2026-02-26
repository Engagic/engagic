import type { RequestHandler } from './$types';

/**
 * Dynamic OG image generator.
 * Renders an SVG-based image and returns it as a PNG-like response.
 *
 * Query params:
 *   title - Main heading text
 *   subtitle - Secondary text (city name, matter file, etc.)
 *   type - Page type: "city" | "meeting" | "matter" | "state" | "home"
 */
export const GET: RequestHandler = async ({ url, setHeaders }) => {
	const title = url.searchParams.get('title') || 'engagic';
	const subtitle = url.searchParams.get('subtitle') || 'Help shape your city';
	const type = url.searchParams.get('type') || 'home';

	// Truncate long titles for rendering
	const maxTitleLen = 80;
	const maxSubLen = 120;
	const displayTitle = title.length > maxTitleLen ? title.slice(0, maxTitleLen - 3) + '...' : title;
	const displaySub = subtitle.length > maxSubLen ? subtitle.slice(0, maxSubLen - 3) + '...' : subtitle;

	// Color scheme per type
	const colors: Record<string, { bg: string; accent: string; badge: string }> = {
		home: { bg: '#0f172a', accent: '#818cf8', badge: 'Civic Intelligence' },
		city: { bg: '#0f172a', accent: '#38bdf8', badge: 'City Council' },
		meeting: { bg: '#0f172a', accent: '#34d399', badge: 'Meeting' },
		matter: { bg: '#0f172a', accent: '#f59e0b', badge: 'Legislation' },
		state: { bg: '#0f172a', accent: '#a78bfa', badge: 'State' },
	};
	const scheme = colors[type] || colors.home;

	// Word-wrap title into lines (rough estimate: ~35 chars per line at this font size)
	const titleLines = wordWrap(displayTitle, 35);
	const titleY = titleLines.length <= 2 ? 260 : 230;

	const svg = `<svg width="1200" height="630" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:${scheme.bg}" />
      <stop offset="100%" style="stop-color:#1e293b" />
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="1200" height="630" fill="url(#bg)" />

  <!-- Subtle grid pattern -->
  <g opacity="0.03">
    ${Array.from({ length: 20 }, (_, i) => `<line x1="${i * 60}" y1="0" x2="${i * 60}" y2="630" stroke="white" stroke-width="1"/>`).join('\n    ')}
    ${Array.from({ length: 11 }, (_, i) => `<line x1="0" y1="${i * 60}" x2="1200" y2="${i * 60}" stroke="white" stroke-width="1"/>`).join('\n    ')}
  </g>

  <!-- Accent bar -->
  <rect x="0" y="0" width="1200" height="4" fill="${scheme.accent}" />

  <!-- Logo -->
  <text x="80" y="100" font-family="monospace" font-size="28" font-weight="700" fill="white">engagic</text>

  <!-- Type badge -->
  <rect x="210" y="78" rx="12" ry="12" width="${scheme.badge.length * 12 + 24}" height="28" fill="${scheme.accent}" opacity="0.2" />
  <text x="${210 + 12}" y="97" font-family="monospace" font-size="14" fill="${scheme.accent}">${escapeXml(scheme.badge)}</text>

  <!-- Title -->
  ${titleLines.map((line, i) => `<text x="80" y="${titleY + i * 52}" font-family="monospace" font-size="42" font-weight="700" fill="white">${escapeXml(line)}</text>`).join('\n  ')}

  <!-- Subtitle -->
  <text x="80" y="${titleY + titleLines.length * 52 + 40}" font-family="monospace" font-size="24" fill="#94a3b8">${escapeXml(displaySub)}</text>

  <!-- Bottom bar -->
  <rect x="0" y="580" width="1200" height="50" fill="rgba(0,0,0,0.3)" />
  <text x="80" y="612" font-family="monospace" font-size="18" fill="#64748b">engagic.org</text>
  <text x="1120" y="612" font-family="monospace" font-size="18" fill="#64748b" text-anchor="end">Civic Intelligence Platform</text>
</svg>`;

	setHeaders({
		'Content-Type': 'image/svg+xml',
		'Cache-Control': 'public, max-age=86400'
	});

	return new Response(svg);
};

function wordWrap(text: string, maxChars: number): string[] {
	const words = text.split(' ');
	const lines: string[] = [];
	let current = '';

	for (const word of words) {
		if (current.length + word.length + 1 > maxChars && current.length > 0) {
			lines.push(current);
			current = word;
		} else {
			current = current ? `${current} ${word}` : word;
		}
	}
	if (current) lines.push(current);
	return lines.length > 0 ? lines : [text];
}

function escapeXml(str: string): string {
	return str
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&apos;');
}

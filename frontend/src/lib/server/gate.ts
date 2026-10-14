/**
 * Content gate shared by every property (engagic, motioncount, spygov).
 *
 * GENERATED COPY: the source is /opt/engagic-ops/gate/gate.ts and the policy
 * is /opt/engagic-ops/scripts/gate_policy.py, which writes this file and
 * gate-policy.json into each frontend. Edit there, then run
 * `uv run /opt/engagic-ops/scripts/gate_policy.py`.
 *
 * A request passes when its path is open (crawl docs, assets, the site's
 * public pages), when it comes from an admitted crawler (operator-published
 * IP range AND matching User-Agent; UA alone is spoofable, range alone
 * matches the operator's other traffic), or when it carries a human cookie
 * from a solved Turnstile. Everything else is content and needs one of those.
 *
 * The cookie is HMAC(secret, `{timestamp}|{ip}`): the visitor IP is mixed
 * into the signature, not carried in the cookie, so one solve cannot be
 * shared across a proxy farm. An IP change means one more invisible solve.
 *
 * Web Crypto only, so it runs in Cloudflare Workers and Node alike.
 */

import policy from './gate-policy.json';

export const COOKIE_NAME = '_ts_human';
export const COOKIE_TTL_SECONDS = 60 * 60 * 24 * 7;

export type GateSite = keyof typeof policy.sites;

/** 'pass' = serve it; 'challenge' = needs a human cookie; 'unconfigured' = no cookie secret. */
export type GateVerdict = 'pass' | 'challenge' | 'unconfigured';

export interface GateRequest {
	pathname: string;
	ip: string | null | undefined;
	userAgent: string | null | undefined;
	cookie: string | undefined;
	secret: string | undefined;
}

const openExact = new Set<string>(policy.open.exact);
const openPrefixes: string[] = policy.open.prefix;
const openExtensions = new Set<string>(policy.open.extensions);
const publicPatterns = {} as Record<GateSite, RegExp[]>;
for (const site of Object.keys(policy.sites) as GateSite[]) {
	publicPatterns[site] = policy.sites[site].public.map((source) => new RegExp(source));
}

export function isOpenPath(site: GateSite, pathname: string): boolean {
	if (openExact.has(pathname)) return true;
	if (openPrefixes.some((prefix) => pathname.startsWith(prefix))) return true;
	const dot = pathname.lastIndexOf('.');
	if (dot > pathname.lastIndexOf('/') && openExtensions.has(pathname.slice(dot + 1).toLowerCase())) return true;
	return publicPatterns[site].some((pattern) => pattern.test(pathname));
}

export async function gateVerdict(site: GateSite, request: GateRequest): Promise<GateVerdict> {
	if (isOpenPath(site, request.pathname)) return 'pass';
	if (admittedCrawler(request.ip, request.userAgent)) return 'pass';
	if (!request.secret) return 'unconfigured';
	return (await verifyCookie(request.secret, request.cookie, request.ip)) ? 'pass' : 'challenge';
}

/**
 * Gated responses must never enter a shared cache. adapter-cloudflare stores
 * every GET response whose Cache-Control is not private/no-cache/no-store in
 * caches.default and serves it BEFORE the app runs, so before this gate: one
 * page rendered for a cookie holder or an admitted crawler was then served
 * to anyone in that colo for its max-age (measured on engagic.org,
 * 2026-10-14). Browsers may still cache it privately for the same max-age.
 */
export function keepPrivate(site: GateSite, pathname: string, response: Response): Response {
	if (isOpenPath(site, pathname)) return response;
	const maxAge = (response.headers.get('cache-control') || '').match(/max-age=\d+/);
	const value = maxAge ? `private, ${maxAge[0]}` : 'private, no-store';
	try {
		response.headers.set('cache-control', value);
		return response;
	} catch {
		// Immutable headers (a fetched Response): copy it.
		const copy = new Response(response.body, response);
		copy.headers.set('cache-control', value);
		return copy;
	}
}

// --- Link previews ---------------------------------------------------------

const previewAgents: string[] = policy.preview_agents;

/** A link-preview fetcher by its UA claim (unverified on purpose; see previewDocument). */
export function isLinkPreview(userAgent: string | null | undefined): boolean {
	if (!userAgent) return false;
	const ua = userAgent.toLowerCase();
	return previewAgents.some((token) => ua.indexOf(token) !== -1);
}

const PREVIEW_TAG =
	/<title>[\s\S]*?<\/title>|<meta\s[^>]*(?:property|name)="(?:og:|twitter:|description")[^>]*>|<link\s[^>]*rel="canonical"[^>]*>/gi;

/** A rendered page reduced to its <head> preview tags, with an empty body:
    enough for a link card, nothing of the record. */
export function previewDocument(html: string): string {
	const end = html.search(/<\/head>/i);
	const tags = (end === -1 ? html : html.slice(0, end)).match(PREVIEW_TAG) || [];
	return (
		'<!doctype html><html><head><meta charset="utf-8"><meta name="robots" content="noindex">' +
		tags.join('') +
		'</head><body></body></html>'
	);
}

// --- Admitted crawlers -----------------------------------------------------

// IPv4 as one unsigned 32-bit number; IPv6 as eight 16-bit groups. Plain
// numbers keep this within the oldest TS lib any of the frontends targets.
interface V4 {
	net: number;
	mask: number;
}

interface V6 {
	groups: number[];
	bits: number;
}

function ipv4ToInt(ip: string): number {
	const parts = ip.split('.');
	if (parts.length !== 4) return -1;
	let n = 0;
	for (const part of parts) {
		const octet = Number(part);
		if (!/^\d{1,3}$/.test(part) || octet > 255) return -1;
		n = n * 256 + octet;
	}
	return n >>> 0;
}

function ipv6Groups(ip: string): number[] | null {
	const halves = ip.split('%')[0].split('::');
	if (halves.length > 2) return null;
	const head = halves[0] ? halves[0].split(':') : [];
	const tail = halves.length === 2 && halves[1] ? halves[1].split(':') : [];
	const missing = halves.length === 2 ? 8 - head.length - tail.length : 0;
	if (missing < 0) return null;
	const groups: string[] = head.concat(new Array(missing).fill('0'), tail);
	if (groups.length !== 8 || !groups.every((group) => /^[0-9a-f]{1,4}$/i.test(group))) return null;
	return groups.map((group) => parseInt(group, 16));
}

function inV6(addr: number[], { groups, bits }: V6): boolean {
	for (let i = 0; i < 8 && bits > i * 16; i++) {
		const keep = Math.min(16, bits - i * 16);
		const mask = (0xffff << (16 - keep)) & 0xffff;
		if ((addr[i] & mask) !== (groups[i] & mask)) return false;
	}
	return true;
}

const crawlers = policy.crawlers.map((crawler) => {
	const v4: V4[] = [];
	const v6: V6[] = [];
	for (const cidr of crawler.prefixes) {
		const [prefix, bits] = cidr.split('/');
		const len = Number(bits);
		if (prefix.indexOf(':') !== -1) {
			const groups = ipv6Groups(prefix);
			if (groups && len >= 0 && len <= 128) v6.push({ groups, bits: len });
		} else {
			const net = ipv4ToInt(prefix);
			if (net === -1 || !(len >= 0 && len <= 32)) continue;
			const mask = len === 0 ? 0 : (0xffffffff << (32 - len)) >>> 0;
			v4.push({ net: (net & mask) >>> 0, mask });
		}
	}
	return { name: crawler.name, token: crawler.ua, v4, v6 };
});

/** Name of the admitted crawler this request verifiably is, else null. Fails closed. */
export function admittedCrawler(ip: string | null | undefined, userAgent: string | null | undefined): string | null {
	if (!ip || !userAgent) return null;
	const ua = userAgent.toLowerCase();
	const claimed = crawlers.filter((crawler) => ua.indexOf(crawler.token) !== -1);
	if (!claimed.length) return null;
	if (ip.indexOf(':') !== -1) {
		const addr = ipv6Groups(ip);
		if (addr === null) return null;
		for (const crawler of claimed) {
			if (crawler.v6.some((net) => inV6(addr, net))) return crawler.name;
		}
		return null;
	}
	const addr = ipv4ToInt(ip);
	if (addr === -1) return null;
	for (const crawler of claimed) {
		if (crawler.v4.some(({ net, mask }) => (addr & mask) >>> 0 === net)) return crawler.name;
	}
	return null;
}

// --- Human cookie ----------------------------------------------------------

async function hmacHex(secret: string, message: string): Promise<string> {
	const encoder = new TextEncoder();
	const key = await crypto.subtle.importKey(
		'raw',
		encoder.encode(secret),
		{ name: 'HMAC', hash: 'SHA-256' },
		false,
		['sign']
	);
	const sig = await crypto.subtle.sign('HMAC', key, encoder.encode(message));
	return Array.from(new Uint8Array(sig))
		.map((b) => b.toString(16).padStart(2, '0'))
		.join('');
}

export async function signCookie(secret: string, timestamp: number, ip: string): Promise<string> {
	const sig = (await hmacHex(secret, `${timestamp}|${ip}`)).slice(0, 32);
	return `${timestamp}:${sig}`;
}

export async function verifyCookie(
	secret: string,
	value: string | undefined,
	ip: string | null | undefined
): Promise<boolean> {
	if (!value || !ip) return false;
	const parts = value.split(':');
	if (parts.length !== 2) return false;
	const ts = Number.parseInt(parts[0], 10);
	if (!Number.isFinite(ts)) return false;
	const now = Math.floor(Date.now() / 1000);
	if (now - ts > COOKIE_TTL_SECONDS || ts > now + 60) return false;
	return timingSafeEqual(value, await signCookie(secret, ts, ip));
}

function timingSafeEqual(a: string, b: string): boolean {
	if (a.length !== b.length) return false;
	let diff = 0;
	for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
	return diff === 0;
}

import type { RequestHandler } from './$types';

function parseRangeHeader(range: string | null, size: number): { offset: number; length: number } | null {
	if (!range) return null;
	const match = range.match(/bytes=(\d+)-(\d*)/);
	if (!match) return null;
	const start = parseInt(match[1], 10);
	const end = match[2] ? parseInt(match[2], 10) : size - 1;
	return { offset: start, length: end - start + 1 };
}

export const GET: RequestHandler = async ({ params, request, platform }) => {
	const key = params.path;

	if (!key) {
		return new Response('Not found', { status: 404 });
	}

	const tiles = platform?.env?.TILES;
	if (!tiles) {
		return new Response('Tiles storage not configured', { status: 503 });
	}

	// First get object metadata to know size for range parsing
	const head = await tiles.head(key);
	if (!head) {
		return new Response('Not found', { status: 404 });
	}

	const rangeHeader = request.headers.get('range');
	const range = parseRangeHeader(rangeHeader, head.size);

	const object = range
		? await tiles.get(key, { range })
		: await tiles.get(key);

	if (!object) {
		return new Response('Not found', { status: 404 });
	}

	const headers = new Headers();
	headers.set('Content-Type', 'application/octet-stream');
	headers.set('Accept-Ranges', 'bytes');
	headers.set('Cache-Control', 'public, max-age=86400');
	headers.set('ETag', head.etag);

	if (range && object.range) {
		const { offset, length } = object.range;
		headers.set('Content-Range', `bytes ${offset}-${offset + length - 1}/${head.size}`);
		headers.set('Content-Length', String(length));
		return new Response(object.body, { status: 206, headers });
	}

	headers.set('Content-Length', String(head.size));
	return new Response(object.body, { status: 200, headers });
};

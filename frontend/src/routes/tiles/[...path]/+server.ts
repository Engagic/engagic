import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params, request, platform }) => {
	const key = params.path;

	if (!key) {
		return new Response('Not found', { status: 404 });
	}

	const tiles = platform?.env?.TILES;
	if (!tiles) {
		return new Response('Tiles storage not configured', { status: 503 });
	}

	const object = await tiles.get(key, {
		range: request.headers.get('range') || undefined
	});

	if (!object) {
		return new Response('Not found', { status: 404 });
	}

	const headers = new Headers();
	headers.set('Content-Type', 'application/octet-stream');
	headers.set('Accept-Ranges', 'bytes');
	headers.set('Cache-Control', 'public, max-age=86400');
	headers.set('ETag', object.etag);

	if (object.range) {
		const { offset, length } = object.range;
		headers.set('Content-Range', `bytes ${offset}-${offset + length - 1}/${object.size}`);
		headers.set('Content-Length', String(length));
		return new Response(object.body, { status: 206, headers });
	}

	headers.set('Content-Length', String(object.size));
	return new Response(object.body, { status: 200, headers });
};

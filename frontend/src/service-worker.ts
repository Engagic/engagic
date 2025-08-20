/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

const sw = self as unknown as ServiceWorkerGlobalScope;

import { build, files, version } from '$service-worker';

// Create a unique cache name for this deployment
const CACHE = `cache-${version}`;

const ASSETS = [
	...build, // the app itself
	...files  // everything in `static`
];

// Cache static assets on install
sw.addEventListener('install', (event) => {
	async function addFilesToCache() {
		const cache = await caches.open(CACHE);
		await cache.addAll(ASSETS);
	}

	event.waitUntil(addFilesToCache());
});

// Remove old caches on activate
sw.addEventListener('activate', (event) => {
	async function deleteOldCaches() {
		for (const key of await caches.keys()) {
			if (key !== CACHE) await caches.delete(key);
		}
	}

	event.waitUntil(deleteOldCaches());
});

// Handle fetch events with network-first strategy for API calls
// and cache-first strategy for static assets
sw.addEventListener('fetch', (event) => {
	if (event.request.method !== 'GET') return;

	async function respond() {
		const url = new URL(event.request.url);
		const cache = await caches.open(CACHE);

		// API calls: network-first with cache fallback
		if (url.origin === 'https://api.engagic.org' || url.pathname.startsWith('/api')) {
			try {
				const response = await fetch(event.request);
				
				// Cache successful API responses
				if (response.status === 200) {
					cache.put(event.request, response.clone());
				}
				
				return response;
			} catch {
				// Fall back to cache for API calls
				const cached = await cache.match(event.request);
				if (cached) return cached;
				
				// Return offline response
				return new Response(
					JSON.stringify({ 
						success: false, 
						message: 'You are offline. Please check your connection.' 
					}),
					{
						status: 503,
						headers: { 'Content-Type': 'application/json' }
					}
				);
			}
		}

		// Static assets: cache-first
		if (ASSETS.includes(url.pathname)) {
			const cached = await cache.match(event.request);
			if (cached) return cached;
		}

		// Everything else: network-first with cache fallback
		try {
			const response = await fetch(event.request);
			
			// Cache successful responses
			if (response.status === 200) {
				cache.put(event.request, response.clone());
			}
			
			return response;
		} catch {
			const cached = await cache.match(event.request);
			if (cached) return cached;
			
			// Return basic offline page for navigation requests
			if (event.request.mode === 'navigate') {
				return cache.match('/offline.html') || new Response('Offline', { status: 503 });
			}
			
			return new Response('Network error', { status: 503 });
		}
	}

	event.respondWith(respond());
});
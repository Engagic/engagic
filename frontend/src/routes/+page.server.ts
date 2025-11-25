import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ setHeaders }) => {
	// Cache this page for 5 minutes
	setHeaders({
		'cache-control': 'public, max-age=300'
	});

	// Analytics fetched client-side to avoid blocking page render
	return {
		analytics: null
	};
};

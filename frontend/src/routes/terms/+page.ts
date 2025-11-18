import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = async () => {
	// Redirect old /terms route to new /about/terms location
	throw redirect(301, '/about/terms');
};

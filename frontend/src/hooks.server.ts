import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
	return resolve(event, {
		preload: ({ type, path }) => {
			if (type === 'font') return path.includes('ibm-plex-mono');
			return type === 'js' || type === 'css';
		}
	});
};

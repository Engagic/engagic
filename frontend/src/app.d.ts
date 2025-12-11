// See https://kit.svelte.dev/docs/types#app
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		interface Locals {
			clientIp: string | null;
			ssrAuthSecret: string | null;
		}
		// interface PageData {}
		// interface PageState {}
		interface Platform {
			env?: {
				TILES: R2Bucket;
				SSR_AUTH_SECRET?: string;
			};
		}
	}
}

export {};

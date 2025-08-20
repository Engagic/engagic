import { writable, derived, get } from 'svelte/store';
import type { SearchResult, Meeting } from './types';
import { apiClient } from './api-client';

// Centralized state management

// Search state
interface SearchState {
	query: string;
	results: SearchResult | null;
	loading: boolean;
	error: string | null;
}

function createSearchStore() {
	const { subscribe, set, update } = writable<SearchState>({
		query: '',
		results: null,
		loading: false,
		error: null
	});
	
	let searchAbortController: AbortController | null = null;
	
	return {
		subscribe,
		setQuery: (query: string) => update(state => ({ ...state, query })),
		
		search: async (query: string) => {
			// Cancel previous search if still running
			if (searchAbortController) {
				searchAbortController.abort();
			}
			
			searchAbortController = new AbortController();
			
			update(state => ({
				...state,
				query,
				loading: true,
				error: null
			}));
			
			try {
				const results = await apiClient.searchMeetings(query);
				
				update(state => ({
					...state,
					results,
					loading: false
				}));
				
				return results;
			} catch (error) {
				const message = error instanceof Error ? error.message : 'Search failed';
				
				update(state => ({
					...state,
					loading: false,
					error: message
				}));
				
				throw error;
			} finally {
				searchAbortController = null;
			}
		},
		
		clear: () => set({
			query: '',
			results: null,
			loading: false,
			error: null
		})
	};
}

// Meeting cache
interface MeetingCache {
	[cityBanana: string]: {
		meetings: Meeting[];
		lastFetched: number;
	};
}

function createMeetingStore() {
	const { subscribe, set, update } = writable<MeetingCache>({});
	
	const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
	
	return {
		subscribe,
		
		getCityMeetings: (cityBanana: string): Meeting[] | null => {
			const cache = get({ subscribe });
			const cached = cache[cityBanana];
			
			if (cached && Date.now() - cached.lastFetched < CACHE_DURATION) {
				return cached.meetings;
			}
			
			return null;
		},
		
		setCityMeetings: (cityBanana: string, meetings: Meeting[]) => {
			update(cache => ({
				...cache,
				[cityBanana]: {
					meetings,
					lastFetched: Date.now()
				}
			}));
		},
		
		clear: () => set({})
	};
}

// Summary cache
interface SummaryCache {
	[meetingId: string]: {
		summary: string;
		lastFetched: number;
	};
}

function createSummaryStore() {
	const { subscribe, set, update } = writable<SummaryCache>({});
	
	return {
		subscribe,
		
		getSummary: (meetingId: string): string | null => {
			const cache = get({ subscribe });
			return cache[meetingId]?.summary || null;
		},
		
		setSummary: (meetingId: string, summary: string) => {
			update(cache => ({
				...cache,
				[meetingId]: {
					summary,
					lastFetched: Date.now()
				}
			}));
		},
		
		clear: () => set({})
	};
}

// Export stores
export const searchStore = createSearchStore();
export const meetingStore = createMeetingStore();
export const summaryStore = createSummaryStore();

// Derived stores for common patterns
export const isSearching = derived(
	searchStore,
	$search => $search.loading
);

export const hasSearchError = derived(
	searchStore,
	$search => !!$search.error
);

export const currentSearchResults = derived(
	searchStore,
	$search => $search.results
);
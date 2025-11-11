import { config, errorMessages } from './config';
import type {
	SearchResult,
	AnalyticsData,
	RandomMeetingResponse,
	RandomMeetingWithItemsResponse,
	TopicSearchResult,
	TickerResponse
} from './types';
import { ApiError, NetworkError } from './types';

// Retry logic for failed requests
async function fetchWithRetry(
	url: string, 
	options: RequestInit = {},
	retries: number = config.maxRetries
): Promise<Response> {
	const controller = new AbortController();
	const timeout = setTimeout(() => controller.abort(), config.requestTimeout);
	
	try {
		const response = await fetch(url, {
			...options,
			signal: controller.signal
		});
		
		clearTimeout(timeout);
		
		if (response.ok) {
			return response;
		}
		
		// Handle specific HTTP errors
		if (response.status === 429) {
			throw new ApiError(errorMessages.rateLimit, 429, true);
		}
		
		if (response.status === 404) {
			throw new ApiError(errorMessages.notFound, 404, false);
		}
		
		// Retry on 5xx errors
		if (response.status >= 500 && retries > 0) {
			await new Promise(resolve => setTimeout(resolve, config.retryDelay));
			return fetchWithRetry(url, options, retries - 1);
		}
		
		throw new ApiError(errorMessages.generic, response.status, false);
		
	} catch (error) {
		clearTimeout(timeout);
		
		if (error instanceof ApiError) {
			throw error;
		}
		
		if (error instanceof Error) {
			if (error.name === 'AbortError') {
				if (retries > 0) {
					await new Promise(resolve => setTimeout(resolve, config.retryDelay));
					return fetchWithRetry(url, options, retries - 1);
				}
				throw new NetworkError(errorMessages.timeout);
			}
			
			if (error.message.includes('fetch')) {
				throw new NetworkError(errorMessages.network);
			}
		}
		
		throw new NetworkError(errorMessages.network);
	}
}

// API client with better error handling
export const apiClient = {
	async searchMeetings(query: string): Promise<SearchResult> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/search`,
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ query }),
			}
		);

		return response.json();
	},

	async getAnalytics(): Promise<AnalyticsData> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/analytics`
		);
		
		return response.json();
	},
	
	async getRandomBestMeeting(): Promise<RandomMeetingResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/random-best-meeting`
		);

		const result = await response.json();

		if (!result.meeting) {
			throw new ApiError('No high-quality meetings available', 404, false);
		}

		return result;
	},

	async getRandomMeetingWithItems(): Promise<RandomMeetingWithItemsResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/random-meeting-with-items`
		);

		return response.json();
	},

	async searchByTopic(topic: string, banana?: string, limit: number = 50): Promise<TopicSearchResult> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/search/by-topic`,
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ topic, banana, limit })
			}
		);

		return response.json();
	},

	async getMeeting(meetingId: string): Promise<{
		success: boolean;
		meeting: any;
		city_name: string | null;
		state: string | null;
		banana: string;
	}> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/meeting/${meetingId}`
		);

		return response.json();
	},

	async getTicker(): Promise<TickerResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/ticker`
		);

		return response.json();
	},

	async generateFlyer(params: {
		meeting_id: string;
		item_id?: string;
		position: 'support' | 'oppose' | 'more_info';
		custom_message?: string;
		user_name?: string;
		dark_mode?: boolean;
	}): Promise<string> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/flyer/generate`,
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(params)
			}
		);

		return response.text();
	},

	async getMatterTimeline(matterId: string): Promise<{
		success: boolean;
		matter: any;
		timeline: Array<{
			item_id: string;
			meeting_id: string;
			meeting_title: string;
			meeting_date: string;
			city_name: string;
			state: string;
			banana: string;
			agenda_number?: string;
			summary?: string;
			topics?: string[];
		}>;
		appearance_count: number;
	}> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/matters/${matterId}/timeline`
		);

		return response.json();
	},

	async getCityMatters(banana: string, limit: number = 50, offset: number = 0): Promise<{
		success: boolean;
		city_name: string;
		state: string;
		banana: string;
		matters: Array<any>;
		total_count: number;
		limit: number;
		offset: number;
	}> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/city/${banana}/matters?limit=${limit}&offset=${offset}`
		);

		return response.json();
	},

	async getStateMatters(stateCode: string, topic?: string, limit: number = 100): Promise<{
		success: boolean;
		state: string;
		cities_count: number;
		cities: Array<{
			banana: string;
			name: string;
			vendor: string;
		}>;
		matters: Array<any>;
		total_matters: number;
		topic_distribution: Record<string, number>;
		filtered_by_topic?: string;
		meeting_stats: {
			total_meetings: number;
			with_agendas: number;
			with_summaries: number;
		};
	}> {
		const url = new URL(`${config.apiBaseUrl}/api/state/${stateCode}/matters`);
		url.searchParams.set('limit', limit.toString());
		if (topic) {
			url.searchParams.set('topic', topic);
		}

		const response = await fetchWithRetry(url.toString());

		return response.json();
	}
};
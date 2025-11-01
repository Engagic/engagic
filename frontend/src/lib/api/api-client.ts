import { config, errorMessages } from './config';
import type {
	SearchResult,
	AnalyticsData,
	RandomMeetingResponse,
	RandomMeetingWithItemsResponse,
	TopicSearchResult
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
	}
};
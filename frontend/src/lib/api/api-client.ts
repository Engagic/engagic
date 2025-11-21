import { config, errorMessages } from './config';
import type {
	SearchResult,
	AnalyticsData,
	RandomMeetingResponse,
	RandomMeetingWithItemsResponse,
	TopicSearchResult,
	TickerResponse,
	MatterTimelineResponse,
	GetMeetingResponse,
	GetCityMattersResponse,
	GetStateMattersResponse
} from './types';
import { ApiError, NetworkError } from './types';

// Request deduplication: Prevent duplicate concurrent calls
const inflightRequests = new Map<string, Promise<any>>();

// Retry logic for failed requests
async function fetchWithRetry(
	url: string,
	options: RequestInit = {},
	retries: number = config.maxRetries,
	clientIp?: string
): Promise<Response> {
	const controller = new AbortController();
	const timeout = setTimeout(() => controller.abort(), config.requestTimeout);

	// Add client IP header if provided (for server-side rate limiting)
	const headers = new Headers(options.headers);
	if (clientIp) {
		headers.set('X-Forwarded-User-IP', clientIp);
	}

	try {
		const response = await fetch(url, {
			...options,
			headers,
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
			return fetchWithRetry(url, options, retries - 1, clientIp);
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
					return fetchWithRetry(url, options, retries - 1, clientIp);
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
	async searchMeetings(query: string, clientIp?: string): Promise<SearchResult> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/search`,
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ query }),
			},
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	async getAnalytics(clientIp?: string): Promise<AnalyticsData> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/analytics`,
			{},
			config.maxRetries,
			clientIp
		);

		return response.json();
	},
	
	async getRandomBestMeeting(clientIp?: string): Promise<RandomMeetingResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/random-best-meeting`,
			{},
			config.maxRetries,
			clientIp
		);

		const result = await response.json();

		if (!result.meeting) {
			throw new ApiError('No high-quality meetings available', 404, false);
		}

		return result;
	},

	async getRandomMeetingWithItems(clientIp?: string): Promise<RandomMeetingWithItemsResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/random-meeting-with-items`,
			{},
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	async searchByTopic(topic: string, banana?: string, limit: number = 50, clientIp?: string): Promise<TopicSearchResult> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/search/by-topic`,
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ topic, banana, limit })
			},
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	async getMeeting(meetingId: string, clientIp?: string): Promise<GetMeetingResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/meeting/${meetingId}`,
			{},
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	async getTicker(clientIp?: string): Promise<TickerResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/ticker`,
			{},
			config.maxRetries,
			clientIp
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
	}, clientIp?: string): Promise<string> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/flyer/generate`,
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(params)
			},
			config.maxRetries,
			clientIp
		);

		return response.text();
	},

	async getMatterTimeline(matterId: string, clientIp?: string): Promise<MatterTimelineResponse> {
		const cacheKey = `timeline:${matterId}`;

		// Return existing in-flight request if one exists
		if (inflightRequests.has(cacheKey)) {
			return inflightRequests.get(cacheKey)!;
		}

		// Create and track new request
		const request = (async () => {
			try {
				const response = await fetchWithRetry(
					`${config.apiBaseUrl}/api/matters/${matterId}/timeline`,
					{},
					config.maxRetries,
					clientIp
				);
				return response.json();
			} finally {
				inflightRequests.delete(cacheKey);
			}
		})();

		inflightRequests.set(cacheKey, request);
		return request;
	},

	async getCityMatters(banana: string, limit: number = 50, offset: number = 0, clientIp?: string): Promise<GetCityMattersResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/city/${banana}/matters?limit=${limit}&offset=${offset}`,
			{},
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	async getStateMatters(stateCode: string, topic?: string, limit: number = 100, clientIp?: string): Promise<GetStateMattersResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/state/${stateCode}/matters`);
		url.searchParams.set('limit', limit.toString());
		if (topic) {
			url.searchParams.set('topic', topic);
		}

		const response = await fetchWithRetry(url.toString(), {}, config.maxRetries, clientIp);

		return response.json();
	},

	async getRandomMatter(clientIp?: string): Promise<{
		success: boolean;
		matter: {
			id: string;
			matter_file: string;
			matter_type: string;
			title: string;
			city_name: string;
			state: string;
			banana: string;
			canonical_summary?: string;
			canonical_topics?: string;
			appearance_count: number;
		};
		timeline: Array<{
			item_id: string;
			meeting_id: string;
			meeting_title: string;
			meeting_date: string;
			agenda_number?: string;
			summary?: string;
			topics?: string[];
		}>;
	}> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/random-matter`,
			{},
			config.maxRetries,
			clientIp
		);

		return response.json();
	}
};
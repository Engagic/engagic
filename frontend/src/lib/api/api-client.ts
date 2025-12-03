import { config, errorMessages } from './config';
import type {
	SearchResult,
	AnalyticsData,
	RandomMeetingResponse,
	RandomMeetingWithItemsResponse,
	TopicSearchResult,
	MatterTimelineResponse,
	GetMeetingResponse,
	GetCityMattersResponse,
	GetStateMattersResponse,
	SearchCityMeetingsResponse,
	SearchCityMattersResponse,
	MatterVotesResponse,
	MeetingVotesResponse,
	CouncilRosterResponse,
	VotingRecordResponse,
	RatingStats,
	RatingSubmitResponse,
	TrendingResponse,
	EngagementStats,
	IssuesResponse,
	ReportIssueResponse,
	IssueType
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
	},

	async searchCityMeetings(banana: string, query: string, limit: number = 50, clientIp?: string): Promise<SearchCityMeetingsResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/city/${banana}/search/meetings`);
		url.searchParams.set('q', query);
		url.searchParams.set('limit', limit.toString());

		const response = await fetchWithRetry(url.toString(), {}, config.maxRetries, clientIp);

		return response.json();
	},

	async searchCityMatters(banana: string, query: string, limit: number = 50, clientIp?: string): Promise<SearchCityMattersResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/city/${banana}/search/matters`);
		url.searchParams.set('q', query);
		url.searchParams.set('limit', limit.toString());

		const response = await fetchWithRetry(url.toString(), {}, config.maxRetries, clientIp);

		return response.json();
	},

	// Vote endpoints
	async getMatterVotes(matterId: string, clientIp?: string): Promise<MatterVotesResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/matters/${matterId}/votes`,
			{},
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	async getMeetingVotes(meetingId: string, clientIp?: string): Promise<MeetingVotesResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/meetings/${meetingId}/votes`,
			{},
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	// Council Member endpoints
	async getCityCouncilMembers(banana: string, clientIp?: string): Promise<CouncilRosterResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/city/${banana}/council-members`,
			{},
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	async getCouncilMemberVotes(memberId: string, limit: number = 100, clientIp?: string): Promise<VotingRecordResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/council-members/${memberId}/votes`);
		url.searchParams.set('limit', limit.toString());

		const response = await fetchWithRetry(url.toString(), {}, config.maxRetries, clientIp);

		return response.json();
	},

	// Rating endpoints
	async getRatingStats(entityType: string, entityId: string, clientIp?: string): Promise<RatingStats> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/${entityType}/${entityId}/rating`,
			{},
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	async submitRating(entityType: string, entityId: string, rating: number, clientIp?: string): Promise<RatingSubmitResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/rate/${entityType}/${entityId}`,
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ rating }),
				credentials: 'include'  // Include session_id cookie for anonymous rating
			},
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	// Issue reporting endpoints
	async getIssues(entityType: string, entityId: string, clientIp?: string): Promise<IssuesResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/${entityType}/${entityId}/issues`,
			{},
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	async reportIssue(entityType: string, entityId: string, issueType: IssueType, description: string, clientIp?: string): Promise<ReportIssueResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/report/${entityType}/${entityId}`,
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ issue_type: issueType, description }),
				credentials: 'include'  // Include session_id cookie
			},
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	// Trending endpoints
	async getTrendingMatters(limit: number = 20, clientIp?: string): Promise<TrendingResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/trending/matters`);
		url.searchParams.set('limit', limit.toString());

		const response = await fetchWithRetry(url.toString(), {}, config.maxRetries, clientIp);

		return response.json();
	},

	// Engagement endpoints
	async getMatterEngagement(matterId: string, clientIp?: string): Promise<EngagementStats> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/matters/${matterId}/engagement`,
			{ credentials: 'include' },
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	async getMeetingEngagement(meetingId: string, clientIp?: string): Promise<EngagementStats> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/meetings/${meetingId}/engagement`,
			{ credentials: 'include' },
			config.maxRetries,
			clientIp
		);

		return response.json();
	},

	// Activity logging (for engagement tracking)
	async logView(entityType: string, entityId: string, clientIp?: string): Promise<void> {
		await fetchWithRetry(
			`${config.apiBaseUrl}/api/activity/view/${entityType}/${entityId}`,
			{
				method: 'POST',
				credentials: 'include'
			},
			config.maxRetries,
			clientIp
		);
	}
};
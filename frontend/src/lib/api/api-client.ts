import { config, errorMessages } from './config';
import type {
	SearchResult,
	AnalyticsData,
	PlatformMetrics,
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
	MatterSponsorsResponse,
	MeetingVotesResponse,
	CouncilRosterResponse,
	VotingRecordResponse,
	CityCommitteesResponse,
	CommitteeDetailResponse,
	CommitteeMembersResponse,
	CommitteeVotesResponse,
	MemberCommitteesResponse,
	RatingStats,
	RatingSubmitResponse,
	EngagementStats,
	IssuesResponse,
	ReportIssueResponse,
	IssueType,
	HappeningResponse
} from './types';
import { ApiError, NetworkError } from './types';

const inflightRequests = new Map<string, Promise<any>>();

// Extra headers for client-side use (browser is single-threaded, safe)
// WARNING: Do NOT use on server-side SSR - use requestHeaders parameter instead
let extraHeaders: Record<string, string> = {};

export function setExtraHeaders(headers: Record<string, string>) {
	extraHeaders = headers;
}

export function getExtraHeaders(): Record<string, string> {
	return extraHeaders;
}

// Request context for server-side use (thread-safe, no global mutation)
// SSR must forward the user's real IP so API can track user journeys correctly
// SSR_AUTH_SECRET authenticates SSR requests to prevent X-Forwarded-Client-IP spoofing
export interface RequestContext {
	clientIp?: string | null;
	ssrAuthSecret?: string | null;
}

export function buildRequestHeaders(context?: RequestContext): Record<string, string> {
	const headers: Record<string, string> = {};
	if (context?.clientIp) {
		headers['X-Forwarded-Client-IP'] = context.clientIp;
		// Include auth secret if available (validates SSR origin)
		if (context.ssrAuthSecret) {
			headers['X-SSR-Auth'] = context.ssrAuthSecret;
		}
	}
	return headers;
}

async function fetchWithRetry(
	url: string,
	options: RequestInit = {},
	retries: number = config.maxRetries,
	requestHeaders?: Record<string, string>
): Promise<Response> {
	const controller = new AbortController();
	const timeout = setTimeout(() => controller.abort(), config.requestTimeout);

	try {
		const response = await fetch(url, {
			...options,
			headers: {
				...extraHeaders,
				...(requestHeaders || {}),
				...(options.headers || {})
			},
			signal: controller.signal
		});

		clearTimeout(timeout);

		if (response.ok) {
			return response;
		}

		if (response.status === 429) {
			throw new ApiError(errorMessages.rateLimit, 429, true);
		}

		if (response.status === 404) {
			throw new ApiError(errorMessages.notFound, 404, false);
		}

		if (response.status >= 500 && retries > 0) {
			await new Promise(resolve => setTimeout(resolve, config.retryDelay));
			return fetchWithRetry(url, options, retries - 1, requestHeaders);
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
					return fetchWithRetry(url, options, retries - 1, requestHeaders);
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
		const response = await fetchWithRetry(`${config.apiBaseUrl}/api/analytics`);
		return response.json();
	},

	async getPlatformMetrics(): Promise<PlatformMetrics> {
		const response = await fetchWithRetry(`${config.apiBaseUrl}/api/platform-metrics`);
		return response.json();
	},

	async getRandomBestMeeting(): Promise<RandomMeetingResponse> {
		const response = await fetchWithRetry(`${config.apiBaseUrl}/api/random-best-meeting`);
		const result = await response.json();
		if (!result.meeting) {
			throw new ApiError('No high-quality meetings available', 404, false);
		}
		return result;
	},

	async getRandomMeetingWithItems(): Promise<RandomMeetingWithItemsResponse> {
		const response = await fetchWithRetry(`${config.apiBaseUrl}/api/random-meeting-with-items`);
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

	async getMeeting(meetingId: string): Promise<GetMeetingResponse> {
		const response = await fetchWithRetry(`${config.apiBaseUrl}/api/meeting/${meetingId}`);
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

	async getMatterTimeline(matterId: string): Promise<MatterTimelineResponse> {
		const cacheKey = `timeline:${matterId}`;

		if (inflightRequests.has(cacheKey)) {
			return inflightRequests.get(cacheKey)!;
		}

		const request = (async () => {
			try {
				const response = await fetchWithRetry(
					`${config.apiBaseUrl}/api/matters/${matterId}/timeline`
				);
				return response.json();
			} finally {
				inflightRequests.delete(cacheKey);
			}
		})();

		inflightRequests.set(cacheKey, request);
		return request;
	},

	async getCityMatters(banana: string, limit: number = 50, offset: number = 0): Promise<GetCityMattersResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/city/${banana}/matters?limit=${limit}&offset=${offset}`
		);
		return response.json();
	},

	async getStateMatters(stateCode: string, topic?: string, limit: number = 100): Promise<GetStateMattersResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/state/${stateCode}/matters`);
		url.searchParams.set('limit', limit.toString());
		if (topic) {
			url.searchParams.set('topic', topic);
		}
		const response = await fetchWithRetry(url.toString());
		return response.json();
	},

	async getRandomMatter(): Promise<{
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
		const response = await fetchWithRetry(`${config.apiBaseUrl}/api/random-matter`);
		return response.json();
	},

	async searchCityMeetings(banana: string, query: string, limit: number = 50): Promise<SearchCityMeetingsResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/city/${banana}/search/meetings`);
		url.searchParams.set('q', query);
		url.searchParams.set('limit', limit.toString());
		const response = await fetchWithRetry(url.toString());
		return response.json();
	},

	async searchCityMatters(banana: string, query: string, limit: number = 50): Promise<SearchCityMattersResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/city/${banana}/search/matters`);
		url.searchParams.set('q', query);
		url.searchParams.set('limit', limit.toString());
		const response = await fetchWithRetry(url.toString());
		return response.json();
	},

	async getMatterVotes(matterId: string): Promise<MatterVotesResponse> {
		const response = await fetchWithRetry(`${config.apiBaseUrl}/api/matters/${matterId}/votes`);
		return response.json();
	},

	async getMatterSponsors(matterId: string): Promise<MatterSponsorsResponse> {
		const response = await fetchWithRetry(`${config.apiBaseUrl}/api/matters/${matterId}/sponsors`);
		return response.json();
	},

	async getMeetingVotes(meetingId: string): Promise<MeetingVotesResponse> {
		const response = await fetchWithRetry(`${config.apiBaseUrl}/api/meetings/${meetingId}/votes`);
		return response.json();
	},

	async getCityCouncilMembers(banana: string): Promise<CouncilRosterResponse> {
		const response = await fetchWithRetry(`${config.apiBaseUrl}/api/city/${banana}/council-members`);
		return response.json();
	},

	async getCouncilMemberVotes(memberId: string, limit: number = 100): Promise<VotingRecordResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/council-members/${memberId}/votes`);
		url.searchParams.set('limit', limit.toString());
		const response = await fetchWithRetry(url.toString());
		return response.json();
	},

	async getMemberCommittees(memberId: string, activeOnly: boolean = true): Promise<MemberCommitteesResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/council-members/${memberId}/committees`);
		url.searchParams.set('active_only', activeOnly.toString());
		const response = await fetchWithRetry(url.toString());
		return response.json();
	},

	async getCityCommittees(banana: string, status?: string): Promise<CityCommitteesResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/city/${banana}/committees`);
		if (status) url.searchParams.set('status', status);
		const response = await fetchWithRetry(url.toString());
		return response.json();
	},

	async getCommittee(committeeId: string): Promise<CommitteeDetailResponse> {
		const response = await fetchWithRetry(`${config.apiBaseUrl}/api/committees/${committeeId}`);
		return response.json();
	},

	async getCommitteeMembers(committeeId: string, activeOnly: boolean = true, asOf?: string): Promise<CommitteeMembersResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/committees/${committeeId}/members`);
		url.searchParams.set('active_only', activeOnly.toString());
		if (asOf) url.searchParams.set('as_of', asOf);
		const response = await fetchWithRetry(url.toString());
		return response.json();
	},

	async getCommitteeVotes(committeeId: string, limit: number = 50): Promise<CommitteeVotesResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/committees/${committeeId}/votes`);
		url.searchParams.set('limit', limit.toString());
		const response = await fetchWithRetry(url.toString());
		return response.json();
	},

	async getRatingStats(entityType: string, entityId: string): Promise<RatingStats> {
		const response = await fetchWithRetry(`${config.apiBaseUrl}/api/${entityType}/${entityId}/rating`);
		return response.json();
	},

	async submitRating(entityType: string, entityId: string, rating: number): Promise<RatingSubmitResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/rate/${entityType}/${entityId}`,
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ rating }),
				credentials: 'include'
			}
		);
		return response.json();
	},

	async getIssues(entityType: string, entityId: string): Promise<IssuesResponse> {
		const response = await fetchWithRetry(`${config.apiBaseUrl}/api/${entityType}/${entityId}/issues`);
		return response.json();
	},

	async reportIssue(entityType: string, entityId: string, issueType: IssueType, description: string): Promise<ReportIssueResponse> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/report/${entityType}/${entityId}`,
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ issue_type: issueType, description }),
				credentials: 'include'
			}
		);
		return response.json();
	},

	async getMatterEngagement(matterId: string): Promise<EngagementStats> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/matters/${matterId}/engagement`,
			{ credentials: 'include' }
		);
		return response.json();
	},

	async getMeetingEngagement(meetingId: string): Promise<EngagementStats> {
		const response = await fetchWithRetry(
			`${config.apiBaseUrl}/api/meetings/${meetingId}/engagement`,
			{ credentials: 'include' }
		);
		return response.json();
	},

	async logView(entityType: string, entityId: string): Promise<void> {
		await fetchWithRetry(
			`${config.apiBaseUrl}/api/activity/view/${entityType}/${entityId}`,
			{
				method: 'POST',
				credentials: 'include'
			}
		);
	},

	async getHappeningItems(banana: string, limit: number = 10): Promise<HappeningResponse> {
		const url = new URL(`${config.apiBaseUrl}/api/city/${banana}/happening`);
		url.searchParams.set('limit', limit.toString());
		const response = await fetchWithRetry(url.toString());
		return response.json();
	}
};

/**
 * Create a server-side API client with request-scoped headers.
 * Use this in +page.server.ts load functions to avoid race conditions.
 *
 * @param clientIp - The real client IP from event.locals.clientIp
 * @param ssrAuthSecret - SSR auth secret to authenticate SSR requests (from $env/static/private)
 * @returns API client methods that include the client IP and auth headers
 */
export function createServerApiClient(clientIp: string | null, ssrAuthSecret?: string | null) {
	const headers = buildRequestHeaders({ clientIp, ssrAuthSecret });

	// Helper to wrap fetch calls with request-scoped headers
	async function serverFetch(url: string, options: RequestInit = {}): Promise<Response> {
		return fetchWithRetry(url, options, config.maxRetries, headers);
	}

	return {
		async searchMeetings(query: string): Promise<SearchResult> {
			const response = await serverFetch(
				`${config.apiBaseUrl}/api/search`,
				{
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ query }),
				}
			);
			return response.json();
		},

		async getMeeting(meetingId: string): Promise<GetMeetingResponse> {
			const response = await serverFetch(`${config.apiBaseUrl}/api/meeting/${meetingId}`);
			return response.json();
		},

		async getMatterTimeline(matterId: string): Promise<MatterTimelineResponse> {
			const response = await serverFetch(
				`${config.apiBaseUrl}/api/matters/${matterId}/timeline`
			);
			return response.json();
		},

		async getCityMatters(banana: string, limit: number = 50, offset: number = 0): Promise<GetCityMattersResponse> {
			const response = await serverFetch(
				`${config.apiBaseUrl}/api/city/${banana}/matters?limit=${limit}&offset=${offset}`
			);
			return response.json();
		},

		async getHappeningItems(banana: string, limit: number = 10): Promise<HappeningResponse> {
			const url = new URL(`${config.apiBaseUrl}/api/city/${banana}/happening`);
			url.searchParams.set('limit', limit.toString());
			const response = await serverFetch(url.toString());
			return response.json();
		},

		async getAnalytics(): Promise<AnalyticsData> {
			const response = await serverFetch(`${config.apiBaseUrl}/api/analytics`);
			return response.json();
		},

		async getPlatformMetrics(): Promise<PlatformMetrics> {
			const response = await serverFetch(`${config.apiBaseUrl}/api/platform-metrics`);
			return response.json();
		},

		async getCityCouncilMembers(banana: string): Promise<CouncilRosterResponse> {
			const response = await serverFetch(`${config.apiBaseUrl}/api/city/${banana}/council-members`);
			return response.json();
		},

		async getCouncilMemberVotes(memberId: string, limit: number = 100): Promise<VotingRecordResponse> {
			const url = new URL(`${config.apiBaseUrl}/api/council-members/${memberId}/votes`);
			url.searchParams.set('limit', limit.toString());
			const response = await serverFetch(url.toString());
			return response.json();
		},

		async getCityCommittees(banana: string, status?: string): Promise<CityCommitteesResponse> {
			const url = new URL(`${config.apiBaseUrl}/api/city/${banana}/committees`);
			if (status) url.searchParams.set('status', status);
			const response = await serverFetch(url.toString());
			return response.json();
		},

		async getCommittee(committeeId: string): Promise<CommitteeDetailResponse> {
			const response = await serverFetch(`${config.apiBaseUrl}/api/committees/${committeeId}`);
			return response.json();
		}
	};
}

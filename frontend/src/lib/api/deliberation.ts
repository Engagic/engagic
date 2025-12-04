import { config } from './config';
import { ApiError } from './types';

export interface Deliberation {
	id: string;
	matter_id: string;
	topic: string | null;
	is_active: boolean;
	created_at?: string;
}

export interface DeliberationComment {
	id: number;
	participant_number: number;
	txt: string;
	created_at?: string;
}

export interface DeliberationStats {
	comment_count: number;
	vote_count: number;
	participant_count: number;
}

export interface ClusterResults {
	n_participants: number;
	n_comments: number;
	k: number;
	positions: [number, number][]; // [x, y] per participant
	clusters: Record<string, number>; // user_id -> cluster_id
	cluster_centers: [number, number][]; // [x, y] per cluster
	consensus: Record<string, number>; // comment_id -> score
	group_votes: Record<
		number,
		Record<number, { A: number; D: number; S: number }>
	>; // cluster -> comment -> votes
	computed_at?: string;
}

export interface GetDeliberationResponse {
	deliberation: Deliberation;
	comments: DeliberationComment[];
	stats: DeliberationStats;
}

export interface GetResultsResponse {
	results: ClusterResults | null;
	message?: string;
}

export interface CreateCommentResponse {
	comment: {
		id: number;
		participant_number: number;
		txt: string;
		is_approved: boolean;
	};
	message: string;
}

export interface VoteResponse {
	success: boolean;
	vote: -1 | 0 | 1;
}

export interface MyVotesResponse {
	votes: Record<number, -1 | 0 | 1>; // comment_id -> vote
}

async function fetchWithAuth(
	url: string,
	options: RequestInit = {},
	accessToken?: string
): Promise<Response> {
	const headers = new Headers(options.headers);
	headers.set('Content-Type', 'application/json');

	if (accessToken) {
		headers.set('Authorization', `Bearer ${accessToken}`);
	}

	const response = await fetch(url, {
		...options,
		headers,
		credentials: 'include' // Include cookies for refresh token fallback
	});

	if (!response.ok) {
		if (response.status === 401) {
			throw new ApiError('Not authenticated', 401, false);
		}
		if (response.status === 404) {
			throw new ApiError('Not found', 404, false);
		}
		if (response.status === 409) {
			const data = await response.json();
			throw new ApiError(data.detail || 'Conflict', 409, false);
		}
		throw new ApiError('Request failed', response.status, false);
	}

	return response;
}

/**
 * Get active deliberation for a matter.
 * Public endpoint - no authentication required.
 */
export async function getDeliberationForMatter(
	matterId: string
): Promise<{ deliberation: Deliberation | null }> {
	const response = await fetch(
		`${config.apiBaseUrl}/api/v1/deliberations/matter/${matterId}`
	);

	if (!response.ok) {
		throw new ApiError('Failed to fetch deliberation', response.status, false);
	}

	return response.json();
}

/**
 * Get deliberation state and approved comments.
 * Public endpoint - no authentication required.
 */
export async function getDeliberation(
	deliberationId: string
): Promise<GetDeliberationResponse> {
	const response = await fetch(
		`${config.apiBaseUrl}/api/v1/deliberations/${deliberationId}`
	);

	if (!response.ok) {
		if (response.status === 404) {
			throw new ApiError('Deliberation not found', 404, false);
		}
		throw new ApiError('Failed to fetch deliberation', response.status, false);
	}

	return response.json();
}

/**
 * Get clustering results for a deliberation.
 * Public endpoint - no authentication required.
 */
export async function getDeliberationResults(
	deliberationId: string
): Promise<GetResultsResponse> {
	const response = await fetch(
		`${config.apiBaseUrl}/api/v1/deliberations/${deliberationId}/results`
	);

	if (!response.ok) {
		throw new ApiError('Failed to fetch results', response.status, false);
	}

	return response.json();
}

/**
 * Create a new deliberation for a matter.
 * Requires authentication.
 */
export async function createDeliberation(
	matterId: string,
	topic?: string,
	accessToken?: string
): Promise<{ deliberation: Deliberation }> {
	const response = await fetchWithAuth(
		`${config.apiBaseUrl}/api/v1/deliberations`,
		{
			method: 'POST',
			body: JSON.stringify({ matter_id: matterId, topic })
		},
		accessToken
	);

	return response.json();
}

/**
 * Submit a comment to a deliberation.
 * Requires authentication. Comments from untrusted users require moderation.
 */
export async function submitComment(
	deliberationId: string,
	txt: string,
	accessToken?: string
): Promise<CreateCommentResponse> {
	const response = await fetchWithAuth(
		`${config.apiBaseUrl}/api/v1/deliberations/${deliberationId}/comments`,
		{
			method: 'POST',
			body: JSON.stringify({ txt })
		},
		accessToken
	);

	return response.json();
}

/**
 * Vote on a comment (agree/pass/disagree).
 * Requires authentication.
 */
export async function voteOnComment(
	deliberationId: string,
	commentId: number,
	vote: -1 | 0 | 1,
	accessToken?: string
): Promise<VoteResponse> {
	const response = await fetchWithAuth(
		`${config.apiBaseUrl}/api/v1/deliberations/${deliberationId}/votes`,
		{
			method: 'POST',
			body: JSON.stringify({ comment_id: commentId, vote })
		},
		accessToken
	);

	return response.json();
}

/**
 * Get current user's votes for a deliberation.
 * Requires authentication.
 */
export async function getMyVotes(
	deliberationId: string,
	accessToken?: string
): Promise<MyVotesResponse> {
	const response = await fetchWithAuth(
		`${config.apiBaseUrl}/api/v1/deliberations/${deliberationId}/my-votes`,
		{},
		accessToken
	);

	return response.json();
}

/**
 * Get pending comments for moderation.
 * Requires authentication (moderator access).
 */
export async function getPendingComments(
	deliberationId: string,
	accessToken?: string
): Promise<{ pending_comments: DeliberationComment[] }> {
	const response = await fetchWithAuth(
		`${config.apiBaseUrl}/api/v1/deliberations/${deliberationId}/pending`,
		{},
		accessToken
	);

	return response.json();
}

/**
 * Approve or hide a pending comment.
 * Requires authentication (moderator access).
 */
export async function moderateComment(
	deliberationId: string,
	commentId: number,
	approve: boolean,
	accessToken?: string
): Promise<{ success: boolean; action: string }> {
	const response = await fetchWithAuth(
		`${config.apiBaseUrl}/api/v1/deliberations/${deliberationId}/moderate`,
		{
			method: 'POST',
			body: JSON.stringify({ comment_id: commentId, approve })
		},
		accessToken
	);

	return response.json();
}

/**
 * Trigger clustering computation for a deliberation.
 * Requires admin authentication.
 */
export async function computeClusters(
	deliberationId: string,
	adminToken: string
): Promise<{ success: boolean; results?: { n_participants: number; n_comments: number; k: number } }> {
	const response = await fetch(
		`${config.apiBaseUrl}/api/v1/deliberations/${deliberationId}/compute`,
		{
			method: 'POST',
			headers: {
				'X-Admin-Token': adminToken
			}
		}
	);

	if (!response.ok) {
		throw new ApiError('Failed to compute clusters', response.status, false);
	}

	return response.json();
}

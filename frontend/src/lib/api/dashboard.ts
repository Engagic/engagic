/**
 * Dashboard API Client
 *
 * Handles dashboard data, digests, and activity feed.
 */

import { config } from './config';
import { ApiError, NetworkError } from './types';
import { getExtraHeaders } from './api-client';

export interface Digest {
	id: string;
	user_id: string;
	name: string;
	cities: string[];
	criteria: {
		keywords: string[];
	};
	frequency: string;
	active: boolean;
	created_at: string;
}

export interface DigestMatch {
	id: string;
	alert_id: string;
	meeting_id: string;
	item_id: string | null;
	match_type: string;
	confidence: number;
	matched_criteria: {
		keyword?: string;
		matter_file?: string;
	};
	notified: boolean;
	created_at: string;
	// Joined data from engagic.db
	city_name?: string;
	city_banana?: string;
	meeting_title?: string;
	meeting_date?: string;
	item_title?: string;
	item_summary?: string;
}

export interface DashboardStats {
	active_digests: number;
	total_matches: number;
	matches_this_week: number;
	cities_tracked: number;
}

export interface DashboardData {
	stats: DashboardStats;
	digests: Digest[];
	recent_matches: DigestMatch[];
}

async function fetchDashboard(
	endpoint: string,
	accessToken: string,
	options: RequestInit = {}
): Promise<Response> {
	const url = `${config.apiBaseUrl}${endpoint}`;
	const controller = new AbortController();
	const timeout = setTimeout(() => controller.abort(), config.requestTimeout);

	try {
		const response = await fetch(url, {
			...options,
			signal: controller.signal,
			headers: {
				...getExtraHeaders(),
				'Authorization': `Bearer ${accessToken}`,
				'Content-Type': 'application/json',
				...options.headers
			}
		});

		clearTimeout(timeout);

		if (!response.ok) {
			const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
			throw new ApiError(error.detail || 'Request failed', response.status);
		}

		return response;
	} catch (err) {
		clearTimeout(timeout);
		if (err instanceof ApiError) throw err;
		if (err instanceof Error && err.name === 'AbortError') {
			throw new NetworkError('Request timeout');
		}
		throw new NetworkError('Network request failed');
	}
}

export async function getDashboard(accessToken: string): Promise<DashboardData> {
	const response = await fetchDashboard('/api/dashboard', accessToken);
	return response.json();
}

export async function updateDigest(
	accessToken: string,
	digestId: string,
	updates: Partial<Digest>
): Promise<Digest> {
	const response = await fetchDashboard(`/api/dashboard/alerts/${digestId}`, accessToken, {
		method: 'PATCH',
		body: JSON.stringify(updates)
	});
	return response.json();
}

export async function addKeywordToDigest(
	accessToken: string,
	digestId: string,
	keyword: string
): Promise<Digest> {
	const response = await fetchDashboard(`/api/dashboard/alerts/${digestId}/keywords`, accessToken, {
		method: 'POST',
		body: JSON.stringify({ keyword })
	});
	return response.json();
}

export async function removeKeywordFromDigest(
	accessToken: string,
	digestId: string,
	keyword: string
): Promise<Digest> {
	const response = await fetchDashboard(`/api/dashboard/alerts/${digestId}/keywords`, accessToken, {
		method: 'DELETE',
		body: JSON.stringify({ keyword })
	});
	return response.json();
}

export async function addCityToDigest(
	accessToken: string,
	digestId: string,
	cityBanana: string
): Promise<Digest> {
	const response = await fetchDashboard(`/api/dashboard/alerts/${digestId}/cities`, accessToken, {
		method: 'POST',
		body: JSON.stringify({ city_banana: cityBanana })
	});
	return response.json();
}

export async function removeCityFromDigest(
	accessToken: string,
	digestId: string,
	cityBanana: string
): Promise<Digest> {
	const response = await fetchDashboard(`/api/dashboard/alerts/${digestId}/cities`, accessToken, {
		method: 'DELETE',
		body: JSON.stringify({ city_banana: cityBanana })
	});
	return response.json();
}

export interface RequestCityResponse {
	success: boolean;
	message: string;
	city_banana: string;
}

export async function requestCity(
	accessToken: string,
	cityBanana: string
): Promise<RequestCityResponse> {
	const response = await fetchDashboard('/api/dashboard/request-city', accessToken, {
		method: 'POST',
		body: JSON.stringify({ city_banana: cityBanana })
	});
	return response.json();
}

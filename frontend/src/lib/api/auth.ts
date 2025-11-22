/**
 * Authentication API Client
 *
 * Handles signup, login, token verification, and logout for userland auth.
 */

import { config } from './config';
import { ApiError, NetworkError } from './types';

export interface SignupRequest {
	name: string;
	email: string;
	city_banana?: string;
	keywords?: string[];
}

export interface SignupResponse {
	message: string;
	user_id: string;
}

export interface LoginRequest {
	email: string;
}

export interface LoginResponse {
	message: string;
}

export interface VerifyTokenResponse {
	access_token: string;
	refresh_token: string;
	user: {
		id: string;
		name: string;
		email: string;
	};
}

export interface RefreshTokenResponse {
	access_token: string;
	refresh_token: string;
	user: {
		id: string;
		name: string;
		email: string;
	};
}

async function fetchAuth(
	endpoint: string,
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

export async function signup(data: SignupRequest): Promise<SignupResponse> {
	const response = await fetchAuth('/api/auth/signup', {
		method: 'POST',
		body: JSON.stringify(data)
	});
	return response.json();
}

export async function login(data: LoginRequest): Promise<LoginResponse> {
	const response = await fetchAuth('/api/auth/login', {
		method: 'POST',
		body: JSON.stringify(data)
	});
	return response.json();
}

export async function verifyToken(token: string): Promise<VerifyTokenResponse> {
	const response = await fetchAuth(`/api/auth/verify?token=${encodeURIComponent(token)}`);
	return response.json();
}

export async function refreshAccessToken(): Promise<RefreshTokenResponse> {
	const response = await fetchAuth('/api/auth/refresh', {
		method: 'POST'
		// Note: refresh_token sent automatically via httpOnly cookie
	});
	return response.json();
}

export async function logout(accessToken: string): Promise<void> {
	await fetchAuth('/api/auth/logout', {
		method: 'POST',
		headers: {
			'Authorization': `Bearer ${accessToken}`
		}
	});
}

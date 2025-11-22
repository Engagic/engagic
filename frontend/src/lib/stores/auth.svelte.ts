/**
 * Authentication Store
 *
 * Manages user authentication state, tokens, and provides helpers
 * for login/logout flows.
 */

import { browser } from '$app/environment';
import * as authApi from '$lib/api/auth';

interface User {
	id: string;
	name: string;
	email: string;
}

interface AuthState {
	user: User | null;
	accessToken: string | null;
	isAuthenticated: boolean;
}

class AuthStore {
	private state = $state<AuthState>({
		user: null,
		accessToken: null,
		isAuthenticated: false
	});

	constructor() {
		if (browser) {
			this.loadFromStorage();
		}
	}

	get user() {
		return this.state.user;
	}

	get accessToken() {
		return this.state.accessToken;
	}

	get isAuthenticated() {
		return this.state.isAuthenticated;
	}

	private loadFromStorage() {
		const user = localStorage.getItem('user');
		const accessToken = localStorage.getItem('access_token');

		if (user && accessToken) {
			this.state.user = JSON.parse(user);
			this.state.accessToken = accessToken;
			this.state.isAuthenticated = true;
		}
	}

	private saveToStorage() {
		if (this.state.user && this.state.accessToken) {
			localStorage.setItem('user', JSON.stringify(this.state.user));
			localStorage.setItem('access_token', this.state.accessToken);
		}
	}

	private clearStorage() {
		localStorage.removeItem('user');
		localStorage.removeItem('access_token');
		// Note: refresh_token is in httpOnly cookie, cleared by server
	}

	async verifyAndLogin(token: string): Promise<void> {
		const response = await authApi.verifyToken(token);
		this.state.user = response.user;
		this.state.accessToken = response.access_token;
		// Note: refresh_token is set as httpOnly cookie by backend
		this.state.isAuthenticated = true;
		this.saveToStorage();
	}

	async refreshToken(): Promise<void> {
		// refresh_token is sent automatically via httpOnly cookie
		const response = await authApi.refreshAccessToken();
		this.state.accessToken = response.access_token;
		this.state.user = response.user;
		this.saveToStorage();
	}

	async logout(): Promise<void> {
		if (this.state.accessToken) {
			try {
				await authApi.logout(this.state.accessToken);
			} catch (err) {
				// Continue logout even if API call fails
				console.error('Logout API call failed:', err);
			}
		}

		this.state.user = null;
		this.state.accessToken = null;
		this.state.isAuthenticated = false;
		this.clearStorage();
		// Note: refresh_token cookie is cleared by backend logout endpoint
	}
}

export const authState = new AuthStore();

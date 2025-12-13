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
	subscribedCities: string[];
}

class AuthStore {
	private state = $state<AuthState>({
		user: null,
		accessToken: null,
		isAuthenticated: false,
		subscribedCities: []
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

	get subscribedCities() {
		return this.state.subscribedCities;
	}

	private loadFromStorage() {
		try {
			const user = localStorage.getItem('user');
			const accessToken = localStorage.getItem('access_token');
			const subscribedCities = localStorage.getItem('subscribed_cities');

			if (user && accessToken) {
				this.state.user = JSON.parse(user);
				this.state.accessToken = accessToken;
				this.state.isAuthenticated = true;
				this.state.subscribedCities = subscribedCities ? JSON.parse(subscribedCities) : [];
			}
		} catch {
			// Corrupted localStorage - clear and start fresh
			this.clearStorage();
		}
	}

	private saveToStorage() {
		if (this.state.user && this.state.accessToken) {
			localStorage.setItem('user', JSON.stringify(this.state.user));
			localStorage.setItem('access_token', this.state.accessToken);
			localStorage.setItem('subscribed_cities', JSON.stringify(this.state.subscribedCities));
		}
	}

	private clearStorage() {
		localStorage.removeItem('user');
		localStorage.removeItem('access_token');
		localStorage.removeItem('subscribed_cities');
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
		this.state.subscribedCities = [];
		this.clearStorage();
		// Note: refresh_token cookie is cleared by backend logout endpoint
	}

	setSubscribedCities(cities: string[]) {
		this.state.subscribedCities = cities;
		this.saveToStorage();
	}

	addSubscribedCity(city: string) {
		if (!this.state.subscribedCities.includes(city)) {
			this.state.subscribedCities = [...this.state.subscribedCities, city];
			this.saveToStorage();
		}
	}

	removeSubscribedCity(city: string) {
		this.state.subscribedCities = this.state.subscribedCities.filter(c => c !== city);
		this.saveToStorage();
	}
}

export const authState = new AuthStore();

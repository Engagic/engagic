<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { authState } from '$lib/stores/auth.svelte';
	import {
		getDashboard,
		addKeywordToDigest,
		removeKeywordFromDigest,
		addCityToDigest,
		removeCityFromDigest,
		requestCity,
		type Digest,
		type DigestMatch
	} from '$lib/api/dashboard';
	import { apiClient } from '$lib/api/api-client';
	import { ApiError, isSearchSuccess, isSearchAmbiguous, type CityOption } from '$lib/api/types';
	import { generateMeetingSlug } from '$lib/utils/utils';

	let loading = $state(true);
	let error = $state<string | null>(null);

	let stats = $state({
		active_digests: 0,
		total_matches: 0,
		matches_this_week: 0,
		cities_tracked: 0
	});

	let digests = $state<Digest[]>([]);
	let recentMatches = $state<DigestMatch[]>([]);

	// Per-digest editing state
	let editingCityForDigest = $state<string | null>(null);
	let citySearchQuery = $state('');
	let citySearchResults = $state<CityOption[]>([]);
	let citySearchLoading = $state(false);
	let citySearchError = $state<string | null>(null);

	// Keyword input state (keyed by digest id)
	let newKeywords = $state<Record<string, string>>({});
	let keywordLoading = $state<Record<string, boolean>>({});
	let keywordError = $state<Record<string, string | null>>({});

	// City operation state
	let cityLoading = $state<Record<string, boolean>>({});
	let cityError = $state<Record<string, string | null>>({});

	onMount(async () => {
		if (!authState.isAuthenticated) {
			goto('/login');
			return;
		}

		try {
			const data = await getDashboard(authState.accessToken!);
			stats = data.stats;
			digests = data.digests;
			recentMatches = data.recent_matches;
		} catch (err) {
			if (err instanceof ApiError && (err.statusCode === 401 || err.statusCode === 403)) {
				await authState.logout();
				goto('/login?expired=true');
				return;
			}
			error = err instanceof Error ? err.message : 'Failed to load dashboard';
		} finally {
			loading = false;
		}
	});

	async function handleLogout() {
		await authState.logout();
		goto('/');
	}

	function formatDate(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		});
	}

	function formatTime(dateStr: string): string {
		const date = new Date(dateStr);
		const now = new Date();
		const diffMs = now.getTime() - date.getTime();
		const diffMins = Math.floor(diffMs / 60000);
		const diffHours = Math.floor(diffMins / 60);
		const diffDays = Math.floor(diffHours / 24);

		if (diffMins < 60) return `${diffMins}m ago`;
		if (diffHours < 24) return `${diffHours}h ago`;
		if (diffDays < 7) return `${diffDays}d ago`;
		return formatDate(dateStr);
	}

	function getMatchLink(match: DigestMatch): string {
		if (!match.meeting_id || !match.city_banana) return '';
		const meeting = {
			id: match.meeting_id,
			title: match.meeting_title || '',
			date: match.meeting_date || ''
		};
		return `/${match.city_banana}/${generateMeetingSlug(meeting as any)}`;
	}

	// Keyword management
	async function handleAddKeyword(digestId: string) {
		const keyword = newKeywords[digestId]?.trim();
		if (!keyword) return;

		const digest = digests.find((d) => d.id === digestId);
		if (!digest) return;
		if (digest.criteria.keywords.length >= 3) {
			keywordError[digestId] = 'Maximum 3 keywords allowed';
			setTimeout(() => (keywordError[digestId] = null), 3000);
			return;
		}

		keywordLoading[digestId] = true;
		keywordError[digestId] = null;

		try {
			const updated = await addKeywordToDigest(authState.accessToken!, digestId, keyword);
			digests = digests.map((d) => (d.id === digestId ? updated : d));
			newKeywords[digestId] = '';
		} catch (err) {
			keywordError[digestId] = err instanceof Error ? err.message : 'Failed to add keyword';
			setTimeout(() => (keywordError[digestId] = null), 3000);
		} finally {
			keywordLoading[digestId] = false;
		}
	}

	async function handleRemoveKeyword(digestId: string, keyword: string) {
		keywordLoading[digestId] = true;
		keywordError[digestId] = null;

		try {
			const updated = await removeKeywordFromDigest(authState.accessToken!, digestId, keyword);
			digests = digests.map((d) => (d.id === digestId ? updated : d));
		} catch (err) {
			keywordError[digestId] = err instanceof Error ? err.message : 'Failed to remove keyword';
			setTimeout(() => (keywordError[digestId] = null), 3000);
		} finally {
			keywordLoading[digestId] = false;
		}
	}

	// City management
	function startCityEdit(digestId: string) {
		editingCityForDigest = digestId;
		citySearchQuery = '';
		citySearchResults = [];
		citySearchError = null;
	}

	function cancelCityEdit() {
		editingCityForDigest = null;
		citySearchQuery = '';
		citySearchResults = [];
		citySearchError = null;
	}

	async function handleCitySearch() {
		if (!citySearchQuery.trim() || !editingCityForDigest) return;

		citySearchLoading = true;
		citySearchError = null;
		citySearchResults = [];

		try {
			const result = await apiClient.searchMeetings(citySearchQuery.trim());
			if (isSearchSuccess(result)) {
				// Direct match - add city immediately
				await handleAddCity(editingCityForDigest, result.banana);
			} else if (isSearchAmbiguous(result)) {
				citySearchResults = result.city_options;
			} else {
				citySearchError = 'City not found. You can request coverage below.';
			}
		} catch (err) {
			citySearchError = err instanceof Error ? err.message : 'Search failed';
		} finally {
			citySearchLoading = false;
		}
	}

	async function handleAddCity(digestId: string, cityBanana: string) {
		cityLoading[digestId] = true;
		cityError[digestId] = null;

		try {
			const updated = await addCityToDigest(authState.accessToken!, digestId, cityBanana);
			digests = digests.map((d) => (d.id === digestId ? updated : d));
			stats.cities_tracked = new Set(digests.reduce<string[]>((acc, d) => acc.concat(d.cities), [])).size;
			cancelCityEdit();
		} catch (err) {
			cityError[digestId] = err instanceof Error ? err.message : 'Failed to add city';
			setTimeout(() => (cityError[digestId] = null), 3000);
		} finally {
			cityLoading[digestId] = false;
		}
	}

	async function handleRemoveCity(digestId: string, cityBanana: string) {
		cityLoading[digestId] = true;
		cityError[digestId] = null;

		try {
			const updated = await removeCityFromDigest(authState.accessToken!, digestId, cityBanana);
			digests = digests.map((d) => (d.id === digestId ? updated : d));
			stats.cities_tracked = new Set(digests.reduce<string[]>((acc, d) => acc.concat(d.cities), [])).size;
		} catch (err) {
			cityError[digestId] = err instanceof Error ? err.message : 'Failed to remove city';
			setTimeout(() => (cityError[digestId] = null), 3000);
		} finally {
			cityLoading[digestId] = false;
		}
	}

	async function handleRequestCity() {
		if (!citySearchQuery.trim() || !editingCityForDigest) return;

		cityLoading[editingCityForDigest] = true;

		try {
			// Convert search query to banana format (rough approximation)
			const banana = citySearchQuery.trim().replace(/[^a-zA-Z]/g, '').toLowerCase();
			await requestCity(authState.accessToken!, banana);
			citySearchError = null;
			cancelCityEdit();
			// Show success feedback
			alert('Request submitted. We will notify you when coverage is added.');
		} catch (err) {
			citySearchError = err instanceof Error ? err.message : 'Failed to request city';
		} finally {
			if (editingCityForDigest) {
				cityLoading[editingCityForDigest] = false;
			}
		}
	}

	function handleKeywordKeydown(event: KeyboardEvent, digestId: string) {
		if (event.key === 'Enter') {
			event.preventDefault();
			handleAddKeyword(digestId);
		}
	}

	function handleCitySearchKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			event.preventDefault();
			handleCitySearch();
		} else if (event.key === 'Escape') {
			cancelCityEdit();
		}
	}
</script>

<svelte:head>
	<title>Dashboard - Engagic</title>
</svelte:head>

<div class="page">
	<div class="container">
		<header class="header">
			<div class="header-content">
				<a href="/" class="logo">engagic</a>
				<h1>Dashboard</h1>
				<div class="header-actions">
					<span class="user-email">{authState.user?.email}</span>
					<button onclick={handleLogout} class="btn-logout">Log Out</button>
				</div>
			</div>
		</header>

		{#if loading}
			<div class="loading">
				<div class="spinner"></div>
				<p>Loading dashboard...</p>
			</div>
		{:else if error}
			<div class="error-banner" role="alert">
				<p>{error}</p>
			</div>
		{:else}
			<!-- Stats -->
			<div class="stats-grid">
				<div class="stat-card">
					<div class="stat-value">{stats.active_digests}</div>
					<div class="stat-label">Active Digests</div>
				</div>
				<div class="stat-card">
					<div class="stat-value">{stats.matches_this_week}</div>
					<div class="stat-label">Matches This Week</div>
				</div>
				<div class="stat-card">
					<div class="stat-value">{stats.cities_tracked}</div>
					<div class="stat-label">Cities Tracked</div>
				</div>
				<div class="stat-card">
					<div class="stat-value">{stats.total_matches}</div>
					<div class="stat-label">Total Matches</div>
				</div>
			</div>

			<!-- Digests Configuration -->
			<section class="section">
				<h2>Your Digests</h2>
				{#if digests.length > 0}
					{#each digests as digest (digest.id)}
						<div class="digest-card">
							<div class="digest-header">
								<h3>{digest.name}</h3>
								<span class="digest-frequency">{digest.frequency}</span>
							</div>
							<div class="digest-details">
								<!-- Cities Section -->
								<div class="digest-section">
									<strong>City:</strong>
									{#if editingCityForDigest === digest.id}
										<div class="city-edit">
											<div class="city-search-row">
												<input
													type="text"
													bind:value={citySearchQuery}
													onkeydown={handleCitySearchKeydown}
													placeholder="Search for a city..."
													class="city-input"
													disabled={citySearchLoading}
												/>
												<button
													onclick={handleCitySearch}
													class="btn-search"
													disabled={citySearchLoading || !citySearchQuery.trim()}
												>
													{citySearchLoading ? '...' : 'Search'}
												</button>
												<button onclick={cancelCityEdit} class="btn-cancel">Cancel</button>
											</div>
											{#if citySearchResults.length > 0}
												<div class="city-results">
													{#each citySearchResults as city}
														<button
															class="city-result"
															onclick={() => handleAddCity(digest.id, city.banana)}
															disabled={cityLoading[digest.id]}
														>
															{city.city_name}, {city.state}
														</button>
													{/each}
												</div>
											{/if}
											{#if citySearchError}
												<div class="field-error">
													{citySearchError}
													{#if citySearchError.includes('not found')}
														<button onclick={handleRequestCity} class="btn-link">
															Request this city
														</button>
													{/if}
												</div>
											{/if}
										</div>
									{:else if digest.cities.length > 0}
										<span class="city-display">
											{#each digest.cities as city}
												<span class="city-tag">
													<a href="/{city}" class="city-link">{city}</a>
													<button
														class="remove-btn"
														onclick={() => handleRemoveCity(digest.id, city)}
														disabled={cityLoading[digest.id]}
														aria-label="Remove {city}"
													>x</button>
												</span>
											{/each}
											<button onclick={() => startCityEdit(digest.id)} class="btn-change">
												Change
											</button>
										</span>
									{:else}
										<button onclick={() => startCityEdit(digest.id)} class="btn-add">
											+ Add a city
										</button>
									{/if}
									{#if cityError[digest.id]}
										<span class="field-error">{cityError[digest.id]}</span>
									{/if}
								</div>

								<!-- Keywords Section -->
								<div class="digest-section">
									<strong>Keywords:</strong>
									<div class="keywords-container">
										{#if digest.criteria.keywords.length > 0}
											<div class="keywords">
												{#each digest.criteria.keywords as keyword}
													<span class="keyword-tag">
														{keyword}
														<button
															class="remove-btn"
															onclick={() => handleRemoveKeyword(digest.id, keyword)}
															disabled={keywordLoading[digest.id]}
															aria-label="Remove {keyword}"
														>x</button>
													</span>
												{/each}
											</div>
										{/if}
										{#if digest.criteria.keywords.length < 3}
											<div class="keyword-input-row">
												<input
													type="text"
													bind:value={newKeywords[digest.id]}
													onkeydown={(e) => handleKeywordKeydown(e, digest.id)}
													placeholder="Add keyword"
													maxlength="50"
													class="keyword-input"
													disabled={keywordLoading[digest.id]}
												/>
												<button
													onclick={() => handleAddKeyword(digest.id)}
													class="btn-add-keyword"
													disabled={keywordLoading[digest.id] || !newKeywords[digest.id]?.trim()}
												>
													{keywordLoading[digest.id] ? '...' : 'Add'}
												</button>
											</div>
										{:else}
											<span class="limit-note">Max 3 keywords</span>
										{/if}
										{#if keywordError[digest.id]}
											<span class="field-error">{keywordError[digest.id]}</span>
										{/if}
									</div>
								</div>
							</div>
						</div>
					{/each}
				{:else}
					<div class="empty-state">
						<p>No digests configured yet.</p>
						<p class="empty-hint">
							Visit a <a href="/">city page</a> and click "Watch this city" to create your first digest.
						</p>
					</div>
				{/if}
			</section>

			<!-- Recent Activity -->
			<section class="section">
				<h2>Recent Matches</h2>
				{#if recentMatches.length > 0}
					<div class="activity-feed">
						{#each recentMatches as match (match.id)}
							{@const link = getMatchLink(match)}
							{#if link}
								<a href={link} class="match-card match-card-link">
									<div class="match-header">
										<h3>{match.city_name || match.city_banana}</h3>
										<span class="match-time">{formatTime(match.created_at)}</span>
									</div>
									<p class="match-meeting">{match.meeting_title}</p>
									{#if match.item_title}
										<p class="match-item">{match.item_title}</p>
									{/if}
									<div class="match-meta">
										<span class="match-type">{match.match_type}</span>
										{#if match.matched_criteria.keyword}
											<span class="matched-keyword">"{match.matched_criteria.keyword}"</span>
										{/if}
									</div>
								</a>
							{:else}
								<div class="match-card">
									<div class="match-header">
										<h3>{match.city_name || match.city_banana}</h3>
										<span class="match-time">{formatTime(match.created_at)}</span>
									</div>
									<p class="match-meeting">{match.meeting_title}</p>
									{#if match.item_title}
										<p class="match-item">{match.item_title}</p>
									{/if}
									<div class="match-meta">
										<span class="match-type">{match.match_type}</span>
										{#if match.matched_criteria.keyword}
											<span class="matched-keyword">"{match.matched_criteria.keyword}"</span>
										{/if}
									</div>
								</div>
							{/if}
						{/each}
					</div>
				{:else}
					<div class="empty-state">
						<p>No matches yet.</p>
						<p class="empty-hint">
							Add keywords to your digest above. When meeting agendas mention your keywords, they will appear here.
						</p>
					</div>
				{/if}
			</section>
		{/if}
	</div>
</div>

<style>
	.page {
		min-height: 100vh;
		background: linear-gradient(135deg, var(--bg-gradient-start) 0%, var(--bg-gradient-end) 100%);
		padding: 2rem;
	}

	.container {
		max-width: 900px;
		margin: 0 auto;
	}

	.header {
		margin-bottom: 2rem;
		padding-bottom: 1rem;
		border-bottom: 1px solid var(--border-primary);
	}

	.header-content {
		display: flex;
		justify-content: space-between;
		align-items: center;
		flex-wrap: wrap;
		gap: 1rem;
	}

	.logo {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		font-weight: 500;
		color: var(--civic-blue);
		text-decoration: none;
		transition: color var(--transition-fast);
	}

	.logo:hover {
		color: var(--civic-accent);
	}

	h1 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.header-actions {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.user-email {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.875rem;
		color: var(--text-secondary);
	}

	.btn-logout {
		padding: 0.5rem 1rem;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: transparent;
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-sm);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-logout:hover {
		background: var(--surface-secondary);
		border-color: var(--civic-gray);
	}

	.loading {
		text-align: center;
		padding: 3rem;
		color: var(--civic-gray);
	}

	.spinner {
		width: 48px;
		height: 48px;
		margin: 0 auto 1rem;
		border: 4px solid var(--border-primary);
		border-top-color: var(--civic-blue);
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.error-banner {
		background: #fef2f2;
		border: 1px solid #fecaca;
		border-radius: var(--radius-md);
		padding: 1rem;
		color: #991b1b;
		text-align: center;
	}

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
		gap: 1rem;
		margin-bottom: 2rem;
	}

	.stat-card {
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-md);
		padding: 1.5rem;
		text-align: center;
		box-shadow: 0 2px 4px var(--shadow-sm);
	}

	.stat-value {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2.5rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin-bottom: 0.5rem;
	}

	.stat-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.section {
		margin-bottom: 2rem;
	}

	h2 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 1rem 0;
	}

	.digest-card {
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-md);
		padding: 1.5rem;
		margin-bottom: 1rem;
		box-shadow: 0 2px 4px var(--shadow-sm);
	}

	.digest-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
	}

	h3 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.digest-frequency {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		padding: 0.25rem 0.75rem;
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		color: var(--text-secondary);
		text-transform: capitalize;
	}

	.digest-details {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.digest-section {
		font-size: 0.875rem;
	}

	.digest-section strong {
		font-family: 'IBM Plex Mono', monospace;
		color: var(--text-primary);
		margin-right: 0.5rem;
	}

	/* City editing */
	.city-edit {
		margin-top: 0.5rem;
	}

	.city-search-row {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.city-input {
		flex: 1;
		padding: 0.5rem 0.75rem;
		font-size: 0.875rem;
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-sm);
		background: var(--surface-primary);
		color: var(--text-primary);
	}

	.city-input:focus {
		outline: none;
		border-color: var(--civic-blue);
	}

	.city-results {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		margin-bottom: 0.5rem;
	}

	.city-result {
		text-align: left;
		padding: 0.5rem 0.75rem;
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-sm);
		color: var(--text-link);
		cursor: pointer;
		font-size: 0.875rem;
		transition: all var(--transition-fast);
	}

	.city-result:hover {
		background: var(--surface-hover);
		border-color: var(--civic-blue);
	}

	.city-display {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.city-tag {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.25rem 0.5rem;
		background: var(--badge-blue-bg);
		color: var(--badge-blue-text);
		border: 1px solid var(--badge-blue-border);
		border-radius: 12px;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8125rem;
	}

	.city-link {
		color: inherit;
		text-decoration: none;
		transition: color var(--transition-fast);
	}

	.city-link:hover {
		color: var(--civic-blue);
		text-decoration: underline;
	}

	/* Keywords */
	.keywords-container {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin-top: 0.25rem;
	}

	.keywords {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.keyword-tag {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.25rem 0.5rem;
		background: var(--badge-blue-bg);
		color: var(--badge-blue-text);
		border: 1px solid var(--badge-blue-border);
		border-radius: 12px;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8125rem;
	}

	.remove-btn {
		background: none;
		border: none;
		color: inherit;
		font-size: 0.875rem;
		cursor: pointer;
		padding: 0 0.25rem;
		opacity: 0.6;
		transition: opacity var(--transition-fast);
	}

	.remove-btn:hover {
		opacity: 1;
	}

	.keyword-input-row {
		display: flex;
		gap: 0.5rem;
	}

	.keyword-input {
		flex: 1;
		max-width: 200px;
		padding: 0.375rem 0.5rem;
		font-size: 0.875rem;
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-sm);
		background: var(--surface-primary);
		color: var(--text-primary);
	}

	.keyword-input:focus {
		outline: none;
		border-color: var(--civic-blue);
	}

	.btn-add-keyword,
	.btn-search {
		padding: 0.375rem 0.75rem;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8125rem;
		font-weight: 500;
		background: var(--civic-blue);
		color: white;
		border: none;
		border-radius: var(--radius-sm);
		cursor: pointer;
		transition: background var(--transition-fast);
	}

	.btn-add-keyword:hover:not(:disabled),
	.btn-search:hover:not(:disabled) {
		background: var(--civic-accent);
	}

	.btn-add-keyword:disabled,
	.btn-search:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-cancel {
		padding: 0.375rem 0.75rem;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8125rem;
		background: transparent;
		color: var(--text-secondary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-sm);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-cancel:hover {
		background: var(--surface-secondary);
	}

	.btn-change,
	.btn-add {
		padding: 0.25rem 0.5rem;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--text-link);
		background: transparent;
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-sm);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-change:hover,
	.btn-add:hover {
		background: var(--surface-secondary);
		border-color: var(--civic-blue);
	}

	.btn-link {
		background: none;
		border: none;
		color: var(--text-link);
		text-decoration: underline;
		cursor: pointer;
		font-size: inherit;
		padding: 0;
		margin-left: 0.5rem;
	}

	.btn-link:hover {
		color: var(--civic-accent);
	}

	.limit-note {
		font-size: 0.75rem;
		color: var(--civic-gray);
		font-style: italic;
	}

	.field-error {
		display: block;
		margin-top: 0.25rem;
		font-size: 0.8125rem;
		color: var(--civic-red);
	}

	.empty-state {
		text-align: center;
		padding: 2rem;
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-md);
	}

	.empty-state p {
		margin: 0;
		color: var(--civic-gray);
	}

	.empty-hint {
		margin-top: 0.5rem !important;
		font-size: 0.875rem;
	}

	.empty-hint a {
		color: var(--text-link);
	}

	.activity-feed {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.match-card {
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-md);
		padding: 1.25rem;
		box-shadow: 0 2px 4px var(--shadow-sm);
	}

	.match-card-link {
		display: block;
		text-decoration: none;
		color: inherit;
		transition: all var(--transition-fast);
	}

	.match-card-link:hover {
		border-color: var(--civic-blue);
		transform: translateY(-2px);
		box-shadow: 0 4px 12px var(--shadow-md);
	}

	.match-header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		margin-bottom: 0.5rem;
	}

	.match-time {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--civic-gray);
	}

	.match-meeting {
		font-size: 0.9375rem;
		color: var(--text-secondary);
		margin: 0.5rem 0;
	}

	.match-item {
		font-size: 0.875rem;
		color: var(--civic-gray);
		margin: 0.25rem 0;
	}

	.match-meta {
		display: flex;
		gap: 0.75rem;
		margin-top: 0.75rem;
	}

	.match-type {
		font-family: 'IBM Plex Mono', monospace;
		padding: 0.25rem 0.75rem;
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		font-size: 0.6875rem;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.matched-keyword {
		font-family: 'IBM Plex Mono', monospace;
		padding: 0.25rem 0.75rem;
		background: var(--badge-blue-bg);
		border: 1px solid var(--badge-blue-border);
		border-radius: 12px;
		font-size: 0.6875rem;
		color: var(--badge-blue-text);
		font-weight: 500;
	}

	@media (max-width: 768px) {
		.page {
			padding: 1rem;
		}

		.stats-grid {
			grid-template-columns: repeat(2, 1fr);
		}

		.digest-header {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.5rem;
		}

		.city-search-row {
			flex-wrap: wrap;
		}

		.city-input {
			width: 100%;
			flex: none;
		}
	}
</style>

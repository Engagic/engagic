<script lang="ts">
	import { signup } from '$lib/api/auth';
	import { authState } from '$lib/stores/auth.svelte';
	import { toastStore } from '$lib/stores/toast.svelte';
	import { getDashboard, addCityToDigest, addKeywordToDigest, removeKeywordFromDigest } from '$lib/api/dashboard';

	interface Props {
		cityName: string;
		cityBanana: string;
		isWatching: boolean;
		open: boolean;
		onClose: () => void;
	}

	let { cityName, cityBanana, isWatching, open = $bindable(), onClose }: Props = $props();

	// Derived: user is authenticated and watching a different city
	const hasOtherCity = $derived(
		authState.isAuthenticated &&
		authState.subscribedCities.length > 0 &&
		!isWatching
	);

	let email = $state('');
	let name = $state('');
	let keywordsInput = $state('');
	let loading = $state(false);
	let success = $state(false);
	let error = $state('');

	// For watching mode - keyword management
	let digestId = $state<string | null>(null);
	let currentKeywords = $state<string[]>([]);
	let newKeyword = $state('');
	let keywordsLoading = $state(false);

	// Fetch current keywords when modal opens for watched city
	// Track request to prevent race conditions on rapid open/close
	let loadRequestId = 0;

	$effect(() => {
		if (open && isWatching && authState.isAuthenticated && authState.accessToken) {
			loadCurrentKeywords();
		}
	});

	async function loadCurrentKeywords() {
		const requestId = ++loadRequestId;
		keywordsLoading = true;
		try {
			const dashboard = await getDashboard(authState.accessToken!);
			// Stale request - modal closed or reopened
			if (requestId !== loadRequestId) return;
			const digest = dashboard.digests.find(d => d.cities.includes(cityBanana));
			if (digest) {
				digestId = digest.id;
				currentKeywords = digest.criteria.keywords || [];
			}
		} catch {
			// Non-fatal: keywords unavailable, user can still manage city
		} finally {
			if (requestId === loadRequestId) {
				keywordsLoading = false;
			}
		}
	}

	async function handleAddKeyword() {
		if (!newKeyword.trim() || !digestId) return;
		if (currentKeywords.length >= 3) {
			error = 'Maximum 3 keywords allowed';
			return;
		}

		const keyword = newKeyword.trim().toLowerCase();
		if (currentKeywords.includes(keyword)) {
			error = 'Keyword already added';
			return;
		}

		error = '';
		keywordsLoading = true;
		try {
			await addKeywordToDigest(authState.accessToken!, digestId, keyword);
			currentKeywords = [...currentKeywords, keyword];
			newKeyword = '';
			toastStore.success('Keyword added');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to add keyword';
		} finally {
			keywordsLoading = false;
		}
	}

	async function handleRemoveKeyword(keyword: string) {
		if (!digestId) return;
		keywordsLoading = true;
		try {
			await removeKeywordFromDigest(authState.accessToken!, digestId, keyword);
			currentKeywords = currentKeywords.filter(k => k !== keyword);
			toastStore.success('Keyword removed');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to remove keyword';
		} finally {
			keywordsLoading = false;
		}
	}

	function isValidEmail(emailStr: string): boolean {
		const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
		return emailRegex.test(emailStr);
	}

	function parseKeywords(input: string): string[] {
		if (!input.trim()) return [];
		return input
			.split(',')
			.map(k => k.trim())
			.filter(k => k.length > 0)
			.slice(0, 3);
	}

	async function handleSwitchCity() {
		// Switch from current city to this one (replaces, 1 city limit)
		error = '';
		loading = true;
		try {
			const dashboardData = await getDashboard(authState.accessToken!);
			if (dashboardData.digests.length > 0) {
				await addCityToDigest(authState.accessToken!, dashboardData.digests[0].id, cityBanana);
				// Replace, not add (1 city limit)
				authState.setSubscribedCities([cityBanana]);
				toastStore.success(`Switched to ${cityName}`);
				onClose();
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to switch city';
		} finally {
			loading = false;
		}
	}

	async function handleSubmit() {
		error = '';

		// New user signup flow
		if (!email.trim()) {
			error = 'Email is required';
			return;
		}

		if (!isValidEmail(email)) {
			error = 'Please enter a valid email address';
			return;
		}

		const keywords = parseKeywords(keywordsInput);
		if (keywords.length > 3) {
			error = 'Maximum 3 keywords allowed';
			return;
		}

		loading = true;

		try {
			await signup({
				email: email.trim(),
				name: name.trim(),
				city_banana: cityBanana,
				keywords: keywords.length > 0 ? keywords : undefined
			});
			success = true;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to create account';
		} finally {
			loading = false;
		}
	}

	function handleClose() {
		if (!loading && !keywordsLoading) {
			onClose();
			setTimeout(() => {
				email = '';
				name = '';
				keywordsInput = '';
				newKeyword = '';
				success = false;
				error = '';
			}, 300);
		}
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div class="modal-overlay" onclick={handleClose} onkeydown={(e) => e.key === 'Escape' && handleClose()} role="presentation">
		<div class="modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="dialog" aria-modal="true" tabindex="-1">
			{#if success}
				<div class="success-state">
					<div class="icon-check">✓</div>
					<h2>Check Your Email</h2>
					<p class="message">
						We've sent a verification link to <strong>{email}</strong>
					</p>
					<p class="hint">
						Click the link to confirm your subscription. The link expires in 15 minutes.
					</p>
				</div>
			{:else if isWatching}
				<button class="close-btn" onclick={handleClose} aria-label="Close">&times;</button>

				<div class="modal-header">
					<div class="watching-badge">Watching</div>
					<h2>{cityName}</h2>
					<p class="subtitle">Manage your keyword alerts for this city.</p>
				</div>

				<div class="keywords-section">
					<label for="new-keyword">Keywords</label>
					{#if currentKeywords.length > 0}
						<div class="keyword-list">
							{#each currentKeywords as keyword (keyword)}
								<span class="keyword-tag">
									{keyword}
									<button
										class="remove-keyword"
										onclick={() => handleRemoveKeyword(keyword)}
										disabled={keywordsLoading}
										aria-label="Remove {keyword}"
									>
										x
									</button>
								</span>
							{/each}
						</div>
					{:else if keywordsLoading}
						<p class="hint-text">Loading...</p>
					{:else}
						<p class="hint-text">No keywords set. Add keywords to get alerts for specific topics.</p>
					{/if}

					{#if currentKeywords.length < 3}
						<div class="add-keyword-row">
							<input
								id="new-keyword"
								type="text"
								bind:value={newKeyword}
								placeholder="Add a keyword..."
								disabled={keywordsLoading}
								class="input"
								onkeydown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddKeyword())}
							/>
							<button
								class="btn-add"
								onclick={handleAddKeyword}
								disabled={keywordsLoading || !newKeyword.trim()}
							>
								Add
							</button>
						</div>
					{/if}
				</div>

				{#if error}
					<div class="error-banner" role="alert">{error}</div>
				{/if}

				<p class="disclaimer">
					Keywords match agenda items in your weekly digest.
				</p>
			{:else if hasOtherCity}
				<button class="close-btn" onclick={handleClose} aria-label="Close">&times;</button>

				<div class="modal-header">
					<h2>Switch to {cityName}?</h2>
					<p class="subtitle">You can only watch one city at a time. Switching will replace your current city.</p>
				</div>

				{#if error}
					<div class="error-banner" role="alert">{error}</div>
				{/if}

				<div class="switch-actions">
					<button class="btn-primary" onclick={handleSwitchCity} disabled={loading}>
						{loading ? 'Switching...' : `Watch ${cityName}`}
					</button>
					<button class="btn-secondary" onclick={handleClose} disabled={loading}>
						Keep current city
					</button>
				</div>
			{:else}
				<button class="close-btn" onclick={handleClose} aria-label="Close">&times;</button>

				<div class="modal-header">
					<h2>Stay engaged with {cityName}</h2>
					<p class="subtitle">Every Sunday, we'll send you:</p>
					<ul class="features">
						<li>What's coming up this week</li>
						<li>How to participate (phone, email, Zoom)</li>
						<li>Items matching your interests (optional)</li>
					</ul>
				</div>

				<form onsubmit={(e) => {e.preventDefault(); handleSubmit();}}>
					<div class="field">
						<label for="name">Name (optional)</label>
						<input
							id="name"
							type="text"
							bind:value={name}
							placeholder="Your name"
							disabled={loading}
							class="input"
							autocomplete="name"
						/>
					</div>

					<div class="field">
						<label for="email">Email</label>
						<input
							id="email"
							type="email"
							bind:value={email}
							placeholder="you@example.com"
							disabled={loading}
							required
							class="input"
							autocomplete="email"
						/>
					</div>

					<div class="field">
						<label for="keywords">Keywords (optional)</label>
						<input
							id="keywords"
							type="text"
							bind:value={keywordsInput}
							placeholder="housing, budget, bike lanes (max 3)"
							disabled={loading}
							class="input"
						/>
						<span class="hint-text">Comma-separated, 1-3 recommended</span>
					</div>

					{#if error}
						<div class="error-banner" role="alert">{error}</div>
					{/if}

					<button type="submit" class="btn-primary" disabled={loading}>
						{loading ? 'Setting up...' : 'Get Ready to Participate'}
					</button>

					<p class="disclaimer">
						Free forever. Unsubscribe anytime.
					</p>
				</form>
			{/if}
		</div>
	</div>
{/if}

<style>
	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.75);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: max(1rem, env(safe-area-inset-top)) max(1rem, env(safe-area-inset-right)) max(1rem, env(safe-area-inset-bottom)) max(1rem, env(safe-area-inset-left));
	}

	.modal {
		background: var(--civic-white);
		border: 1px solid var(--civic-border);
		border-radius: 12px;
		padding: 2rem;
		max-width: 480px;
		width: 100%;
		max-height: 90vh;
		overflow-y: auto;
		position: relative;
		box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3);
	}

	.close-btn {
		position: absolute;
		top: 1rem;
		right: 1rem;
		background: transparent;
		border: none;
		font-size: 2rem;
		color: var(--civic-gray);
		cursor: pointer;
		padding: 0;
		width: 32px;
		height: 32px;
		line-height: 1;
		transition: color 0.2s;
	}

	.close-btn:hover {
		color: var(--civic-dark);
	}

	.modal-header {
		margin-bottom: 1.5rem;
	}

	.watching-badge {
		display: inline-block;
		padding: 0.25rem 0.75rem;
		background: var(--civic-green);
		color: white;
		font-size: 0.75rem;
		font-weight: 600;
		border-radius: 9999px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 0.5rem;
	}

	h2 {
		font-size: 1.5rem;
		font-weight: bold;
		color: var(--civic-dark);
		margin: 0 0 0.75rem 0;
	}

	.subtitle {
		font-size: 0.9375rem;
		color: var(--civic-gray);
		margin: 0 0 0.5rem 0;
	}

	.features {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.features li {
		font-size: 0.875rem;
		color: var(--civic-gray);
		padding-left: 1.5rem;
		position: relative;
	}

	.features li::before {
		content: '✓';
		position: absolute;
		left: 0;
		color: var(--civic-blue);
		font-weight: bold;
	}

	.keywords-section {
		margin-bottom: 1.5rem;
	}

	.keywords-section label {
		display: block;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--civic-dark);
		margin-bottom: 0.5rem;
	}

	.keyword-list {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.keyword-tag {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.375rem 0.75rem;
		background: var(--surface-secondary);
		border: 1px solid var(--civic-border);
		border-radius: 9999px;
		font-size: 0.875rem;
		color: var(--civic-dark);
	}

	.remove-keyword {
		background: transparent;
		border: none;
		color: var(--civic-gray);
		font-size: 0.875rem;
		line-height: 1;
		padding: 0;
		cursor: pointer;
		transition: color 0.2s;
	}

	.remove-keyword:hover {
		color: var(--civic-red);
	}

	.remove-keyword:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.add-keyword-row {
		display: flex;
		gap: 0.5rem;
	}

	.add-keyword-row .input {
		flex: 1;
	}

	.btn-add {
		padding: 0.75rem 1.25rem;
		font-size: 0.875rem;
		font-weight: 600;
		background: var(--civic-blue);
		color: white;
		border: none;
		border-radius: 8px;
		cursor: pointer;
		transition: all 0.2s;
		white-space: nowrap;
	}

	.btn-add:hover:not(:disabled) {
		background: var(--civic-accent);
	}

	.btn-add:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.switch-actions {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.field {
		margin-bottom: 1.25rem;
	}

	label {
		display: block;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--civic-dark);
		margin-bottom: 0.5rem;
	}

	.input {
		width: 100%;
		padding: 0.75rem 1rem;
		font-size: 1rem;
		font-family: system-ui, -apple-system, sans-serif;
		color: var(--text-primary);
		background: var(--surface-primary);
		border: 2px solid var(--civic-border);
		border-radius: 8px;
		transition: all 0.2s;
	}

	.input:focus {
		outline: none;
		border: 2px solid var(--civic-blue);
		box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
	}

	.input:disabled {
		opacity: 0.5;
		cursor: not-allowed;
		background: var(--civic-light);
	}

	.hint-text {
		display: block;
		font-size: 0.8125rem;
		color: var(--civic-gray);
		margin-top: 0.375rem;
	}

	.error-banner {
		padding: 0.75rem;
		background: #fef2f2;
		border: 1px solid #ef4444;
		border-radius: 8px;
		color: #991b1b;
		font-size: 0.875rem;
		margin-bottom: 1.25rem;
		font-weight: 500;
	}

	.btn-primary {
		width: 100%;
		padding: 1rem 1.5rem;
		font-size: 1rem;
		font-weight: 600;
		background: var(--civic-blue);
		color: white;
		border: none;
		border-radius: 8px;
		cursor: pointer;
		transition: all 0.2s;
		font-family: system-ui, -apple-system, sans-serif;
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--civic-accent);
		transform: translateY(-2px);
		box-shadow: 0 4px 12px rgba(139, 92, 246, 0.3);
	}

	.btn-primary:disabled {
		opacity: 0.5;
		cursor: not-allowed;
		transform: none;
	}

	.btn-secondary {
		width: 100%;
		padding: 1rem 1.5rem;
		font-size: 1rem;
		font-weight: 600;
		background: transparent;
		color: var(--civic-gray);
		border: 1px solid var(--civic-border);
		border-radius: 8px;
		cursor: pointer;
		transition: all 0.2s;
		font-family: system-ui, -apple-system, sans-serif;
	}

	.btn-secondary:hover:not(:disabled) {
		background: var(--surface-secondary);
		color: var(--civic-dark);
	}

	.btn-secondary:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.disclaimer {
		text-align: center;
		margin-top: 1rem;
		font-size: 0.8125rem;
		color: var(--civic-gray);
		font-style: italic;
	}

	.success-state {
		text-align: center;
		padding: 2rem 0;
	}

	.icon-check {
		width: 64px;
		height: 64px;
		margin: 0 auto 1.5rem;
		background: #d1fae5;
		border: 1px solid #10b981;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 2rem;
		color: #10b981;
		font-weight: bold;
	}

	.message {
		font-size: 1rem;
		color: var(--civic-gray);
		margin: 0.75rem 0;
	}

	.message strong {
		color: var(--civic-blue);
		font-weight: 600;
	}

	.hint {
		font-size: 0.875rem;
		color: var(--civic-gray);
		margin: 0.5rem 0 0 0;
	}

	@media (max-width: 640px) {
		.modal {
			padding: 1.5rem;
		}

		h2 {
			font-size: 1.25rem;
		}

		.icon-check {
			width: 56px;
			height: 56px;
			font-size: 1.75rem;
		}

		.add-keyword-row {
			flex-direction: column;
		}

		.btn-add {
			width: 100%;
		}
	}
</style>

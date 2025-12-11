<script lang="ts">
	import { signup } from '$lib/api/auth';
	import { authState } from '$lib/stores/auth.svelte';
	import { getDashboard, addCityToDigest } from '$lib/api/dashboard';

	interface Props {
		cityName: string;
		cityBanana: string;
		open: boolean;
		onClose: () => void;
	}

	let { cityName, cityBanana, open = $bindable(), onClose }: Props = $props();

	let email = $state('');
	let name = $state('');
	let keywordsInput = $state('');
	let loading = $state(false);
	let success = $state(false);
	let error = $state('');

	function isValidEmail(email: string): boolean {
		const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
		return emailRegex.test(email);
	}

	function parseKeywords(input: string): string[] {
		if (!input.trim()) return [];
		return input
			.split(',')
			.map(k => k.trim())
			.filter(k => k.length > 0)
			.slice(0, 3); // Max 3 keywords
	}

	async function handleSubmit() {
		error = '';

		// If already logged in, just add city to existing digest
		if (authState.isAuthenticated) {
			loading = true;
			try {
				const dashboardData = await getDashboard(authState.accessToken!);

				if (dashboardData.digests.length > 0) {
					await addCityToDigest(authState.accessToken!, dashboardData.digests[0].id, cityBanana);
					success = true;
					setTimeout(() => {
						onClose();
						success = false;
					}, 2000);
				}
			} catch (err) {
				error = err instanceof Error ? err.message : 'Failed to add city';
			} finally {
				loading = false;
			}
			return;
		}

		// New user signup flow
		if (!email.trim()) {
			error = 'Email is required';
			return;
		}

		if (!isValidEmail(email)) {
			error = 'Please enter a valid email address';
			return;
		}

		// Name is optional - skip validation

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
			console.error('Signup error:', err);
		} finally {
			loading = false;
		}
	}

	function handleClose() {
		if (!loading) {
			onClose();
			// Reset state after modal closes
			setTimeout(() => {
				email = '';
				name = '';
				keywordsInput = '';
				success = false;
				error = '';
			}, 300);
		}
	}
</script>

{#if open}
	<div class="modal-overlay" onclick={handleClose} role="presentation">
		<div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
			{#if success}
				<div class="success-state">
					<div class="icon-check">✓</div>
					<h2>{authState.isAuthenticated ? 'Watching ' + cityName : 'Check Your Email'}</h2>
					{#if authState.isAuthenticated}
						<p>Every Sunday, you'll know what's happening and how to speak up.</p>
					{:else}
						<p class="message">
							We've sent a verification link to <strong>{email}</strong>
						</p>
						<p class="hint">
							Click the link to confirm your subscription. The link expires in 15 minutes.
						</p>
					{/if}
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
					{#if !authState.isAuthenticated}
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
					{/if}

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
						{loading ? 'Setting up...' : authState.isAuthenticated ? 'Start Watching' : 'Get Ready to Participate'}
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
		color: var(--civic-dark);
		background: white;
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
	}
</style>

<script lang="ts">
	import { signup } from '$lib/api/auth';
	import { page } from '$app/stores';
	import { logger } from '$lib/services/logger';
	import { onMount } from 'svelte';

	let email = $state('');
	let name = $state('');
	let loading = $state(false);
	let success = $state(false);
	let error = $state('');

	// Get city from query params (from 404 page redirect)
	const cityBanana = $derived($page.url.searchParams.get('city') || '');
	const cityDisplayName = $derived($page.url.searchParams.get('name') || '');

	onMount(() => {
		logger.trackEvent('signup_view', { source: cityBanana ? 'city_request' : 'direct' });
	});

	function isValidEmail(email: string): boolean {
		const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
		return emailRegex.test(email);
	}

	async function handleSubmit() {
		error = '';

		if (!email.trim()) {
			error = 'Email is required';
			return;
		}

		if (!isValidEmail(email)) {
			error = 'Please enter a valid email address';
			return;
		}

		if (!name.trim()) {
			error = 'Name is required';
			return;
		}

		loading = true;

		try {
			await signup({
				email: email.trim(),
				name: name.trim(),
				city_banana: cityBanana || undefined
			});
			success = true;
			logger.trackEvent('signup_submit', { source: cityBanana ? 'city_request' : 'direct' });
		} catch (err: Error | unknown) {
			error = err instanceof Error ? err.message : 'Failed to create account';
			logger.error('Signup error', {}, err instanceof Error ? err : undefined);
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Sign Up - Engagic</title>
	<meta
		name="description"
		content="Create a free Engagic account. Stay informed about local government and make your voice heard."
	/>
</svelte:head>

<div class="page">
	<div class="container">
		{#if success}
			<div class="card success-state">
				<div class="icon-wrapper">
					<div class="icon-check" aria-hidden="true">✓</div>
				</div>
				<h1>Check Your Email</h1>
				<p class="message">
					We've sent a verification link to <strong>{email}</strong>
				</p>
				<p class="hint">
					Click the link in the email to access your dashboard. The link expires in 15 minutes.
				</p>
				{#if cityDisplayName}
					<p class="watching-confirmation">
						You're now watching {cityDisplayName}. We'll email you when we add coverage.
					</p>
				{/if}
			</div>
		{:else}
			<div class="card">
				{#if cityDisplayName}
					<div class="city-context">
						<span class="city-badge">Watching: {cityDisplayName}</span>
					</div>
					<h1>Get Notified</h1>
					<p class="subtitle">We'll email you when we add {cityDisplayName} to our coverage.</p>
				{:else}
					<h1>Get Started</h1>
					<p class="subtitle">Know what's happening. Have your say. Set up in 30 seconds.</p>
				{/if}

				<form onsubmit={(e) => {e.preventDefault(); handleSubmit();}}>
					<div class="field">
						<label for="name">Name</label>
						<input
							id="name"
							type="text"
							bind:value={name}
							placeholder="Your name"
							disabled={loading}
							required
							class="input"
							autocomplete="name"
							aria-describedby={error ? 'error-message' : undefined}
							aria-invalid={!!error}
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
							aria-describedby={error ? 'error-message' : undefined}
							aria-invalid={!!error}
						/>
					</div>

					{#if error}
						<div class="error-banner" role="alert" id="error-message">{error}</div>
					{/if}

					<button type="submit" class="btn-primary" disabled={loading}>
						{loading ? 'Creating account...' : 'Create Free Account'}
					</button>

					<p class="footer-text">
						Already have an account? <a href="/login">Log in</a>
					</p>

					<p class="free-forever">
						Free forever. Add cities and keywords after signup.
					</p>
				</form>
			</div>
		{/if}
	</div>
</div>

<style>
	.page {
		min-height: 100vh;
		background: linear-gradient(135deg, var(--bg-gradient-start) 0%, var(--bg-gradient-end) 100%);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 2rem;
	}

	.container {
		width: 100%;
		max-width: 480px;
	}

	.card {
		background: var(--civic-white);
		border: 1px solid var(--civic-border);
		border-radius: 12px;
		padding: 2.5rem;
		box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
	}

	.success-state {
		text-align: center;
	}

	.icon-wrapper {
		display: flex;
		justify-content: center;
		margin-bottom: 1.5rem;
	}

	.icon-check {
		width: 64px;
		height: 64px;
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

	.city-context {
		margin-bottom: 1rem;
	}

	.city-badge {
		display: inline-block;
		padding: 0.5rem 1rem;
		background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
		border: 1px solid var(--civic-blue);
		border-radius: 20px;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--civic-blue);
	}

	h1 {
		font-size: 1.875rem;
		font-weight: bold;
		margin: 0 0 0.75rem 0;
		color: var(--civic-dark);
		letter-spacing: -0.02em;
	}

	.subtitle {
		font-size: 1rem;
		color: var(--civic-gray);
		margin: 0 0 2rem 0;
		line-height: 1.5;
	}

	.message {
		font-size: 1.125rem;
		color: var(--civic-gray);
		margin: 0 0 1rem 0;
		line-height: 1.6;
	}

	.message strong {
		color: var(--civic-blue);
		font-weight: 600;
	}

	.hint {
		font-size: 0.875rem;
		color: var(--civic-gray);
		margin: 0;
		line-height: 1.6;
	}

	.watching-confirmation {
		font-size: 0.875rem;
		color: #059669;
		font-weight: 500;
		margin: 1rem 0 0 0;
		padding: 0.75rem 1rem;
		background: #ecfdf5;
		border: 1px solid #a7f3d0;
		border-radius: 8px;
		line-height: 1.5;
	}

	.field {
		margin-bottom: 1.5rem;
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

	.input::placeholder {
		color: #9ca3af;
	}

	.error-banner {
		padding: 1rem;
		background: #fef2f2;
		border: 1px solid #ef4444;
		border-radius: 8px;
		color: #991b1b;
		font-size: 0.875rem;
		margin-bottom: 1.5rem;
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

	.btn-primary:active:not(:disabled) {
		transform: translateY(0);
	}

	.btn-primary:disabled {
		opacity: 0.5;
		cursor: not-allowed;
		transform: none;
	}

	.footer-text {
		text-align: center;
		margin-top: 1.5rem;
		font-size: 0.875rem;
		color: var(--civic-gray);
	}

	.footer-text a {
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 600;
		transition: color 0.2s;
	}

	.footer-text a:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}

	.free-forever {
		text-align: center;
		margin-top: 1rem;
		font-size: 0.8125rem;
		color: var(--civic-gray);
		font-style: italic;
	}

	@media (max-width: 640px) {
		.page {
			padding: 1rem;
		}

		.card {
			padding: 1.5rem;
		}

		h1 {
			font-size: 1.5rem;
		}

		.icon-check {
			width: 56px;
			height: 56px;
			font-size: 1.5rem;
		}
	}

	:global(.dark) .error-banner {
		background: #450a0a;
		border-color: #991b1b;
		color: #fca5a5;
	}
</style>

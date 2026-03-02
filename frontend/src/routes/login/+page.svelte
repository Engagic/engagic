<script lang="ts">
	import { login } from '$lib/api/auth';
	import { logger } from '$lib/services/logger';
	import { page } from '$app/stores';

	let email = $state('');
	let loading = $state(false);
	let success = $state(false);
	let error = $state('');

	// Check for expired session redirect
	const sessionExpired = $derived($page.url.searchParams.get('expired') === 'true');

	function isValidEmail(email: string): boolean {
		const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
		return emailRegex.test(email);
	}

	async function handleLogin() {
		error = '';

		if (!email.trim()) {
			error = 'Email is required';
			return;
		}

		if (!isValidEmail(email)) {
			error = 'Please enter a valid email address';
			return;
		}

		loading = true;

		try {
			await login({ email: email.trim() });
			success = true;
		} catch (err: Error | unknown) {
			if (err instanceof Error && err.message?.includes('No account found')) {
				error = 'No account found with this email. Please sign up first.';
			} else {
				error = err instanceof Error ? err.message : 'Failed to send login link';
			}
			logger.error('Login error', {}, err instanceof Error ? err : undefined);
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Log In - Engagic</title>
	<meta
		name="description"
		content="Log in to your Engagic account. Track city council meetings and stay updated on civic issues."
	/>
</svelte:head>

<div class="page">
	<div class="container">
		<a href="/" class="home-link">← engagic</a>
		{#if success}
			<div class="card success-state">
				<div class="icon-wrapper">
					<div class="icon-check" aria-hidden="true">✓</div>
				</div>
				<h1>Check Your Email</h1>
				<p class="message">
					We've sent a magic link to <strong>{email}</strong>
				</p>
				<p class="hint">
					Click the link in the email to access your dashboard. The link expires in 15 minutes.
				</p>
			</div>
		{:else}
			<div class="card">
				{#if sessionExpired}
					<div class="session-expired-banner" role="alert">
						Your session has expired. Please log in again.
					</div>
				{/if}
				<h1>Welcome Back</h1>
				<p class="subtitle">Enter your email to receive a login link</p>

				<form onsubmit={(e) => {e.preventDefault(); handleLogin();}}>
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
						{loading ? 'Sending...' : 'Send Login Link'}
					</button>

					<p class="footer-text">
						Don't have an account? <a href="/signup">Sign up</a>
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
		max-width: var(--width-auth);
	}

	.home-link {
		display: inline-block;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--civic-blue);
		text-decoration: none;
		margin-bottom: 1.5rem;
		transition: color var(--transition-fast);
	}

	.home-link:hover {
		color: var(--civic-accent);
	}

	.card {
		background: var(--civic-white);
		border: 1px solid var(--civic-border);
		border-radius: var(--radius-lg);
		padding: 2.5rem;
		box-shadow: 0 8px 16px var(--shadow-md);
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
		background: var(--success-bg);
		border: 1px solid var(--success-border);
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 2rem;
		color: var(--success-border);
		font-weight: bold;
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
		font-family: 'IBM Plex Sans', sans-serif;
		color: var(--text-primary);
		background: var(--surface-primary);
		border: 2px solid var(--civic-border);
		border-radius: var(--radius-md);
		transition: all var(--transition-normal);
	}

	.input:focus {
		outline: none;
		border: 2px solid var(--civic-blue);
		box-shadow: 0 0 0 3px var(--shadow-sm);
	}

	.input:disabled {
		opacity: 0.5;
		cursor: not-allowed;
		background: var(--civic-light);
	}

	.input::placeholder {
		color: var(--civic-gray);
	}

	.error-banner {
		padding: 1rem;
		background: var(--error-bg);
		border: 1px solid var(--error-border);
		border-radius: var(--radius-md);
		color: var(--error-text);
		font-size: 0.875rem;
		margin-bottom: 1.5rem;
		font-weight: 500;
	}

	.session-expired-banner {
		padding: 1rem;
		background: var(--warning-bg);
		border: 1px solid var(--warning-border);
		border-radius: var(--radius-md);
		color: var(--warning-text);
		font-size: 0.875rem;
		margin-bottom: 1.5rem;
		font-weight: 500;
		text-align: center;
	}

	.btn-primary {
		width: 100%;
		padding: 1rem 1.5rem;
		font-size: 1rem;
		font-weight: 600;
		background: var(--civic-blue);
		color: white;
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
		transition: all var(--transition-normal);
		font-family: 'IBM Plex Sans', sans-serif;
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--civic-accent);
		transform: translateY(-2px);
		box-shadow: 0 4px 12px var(--shadow-lg);
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
		transition: color var(--transition-normal);
	}

	.footer-text a:hover {
		color: var(--civic-accent);
		text-decoration: underline;
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

</style>

<script lang="ts">
	import { signup } from '$lib/api/auth';

	let email = $state('');
	let name = $state('');
	let loading = $state(false);
	let success = $state(false);
	let error = $state('');

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
				name: name.trim()
			});
			success = true;
		} catch (err: Error | unknown) {
			error = err instanceof Error ? err.message : 'Failed to create account';
			console.error('Signup error:', err);
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Sign Up - Engagic</title>
	<meta
		name="description"
		content="Create a free Engagic account. Get alerts when your city discusses topics you care about."
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
			</div>
		{:else}
			<div class="card">
				<h1>Get Started</h1>
				<p class="subtitle">Free civic alerts for everyone. Set up your account in 30 seconds.</p>

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
		background: var(--color-bg-primary);
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
		background: var(--color-bg-primary);
		border: 1px solid var(--color-border);
		border-radius: 12px;
		padding: 2.5rem;
		box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
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

	h1 {
		font-size: 1.875rem;
		font-weight: bold;
		margin: 0 0 0.75rem 0;
		color: var(--color-text-primary);
		letter-spacing: -0.02em;
	}

	.subtitle {
		font-size: 1rem;
		color: var(--color-text-secondary);
		margin: 0 0 2rem 0;
		line-height: 1.5;
	}

	.message {
		font-size: 1.125rem;
		color: var(--color-text-secondary);
		margin: 0 0 1rem 0;
		line-height: 1.6;
	}

	.message strong {
		color: var(--color-primary);
		font-weight: 600;
	}

	.hint {
		font-size: 0.875rem;
		color: var(--color-text-tertiary);
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
		color: var(--color-text-primary);
		margin-bottom: 0.5rem;
	}

	.input {
		width: 100%;
		padding: 0.75rem 1rem;
		font-size: 1rem;
		font-family: system-ui, -apple-system, sans-serif;
		color: var(--color-text-primary);
		background: var(--color-bg-primary);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		transition: all 0.2s;
	}

	.input:focus {
		outline: none;
		border: 2px solid var(--color-primary);
		padding: calc(0.75rem - 1px) calc(1rem - 1px);
		box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.1);
	}

	.input:disabled {
		opacity: 0.5;
		cursor: not-allowed;
		background: var(--color-bg-secondary);
	}

	.input::placeholder {
		color: var(--color-text-tertiary);
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
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: 8px;
		cursor: pointer;
		transition: all 0.2s;
		font-family: system-ui, -apple-system, sans-serif;
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--color-primary-hover);
		transform: translateY(-2px);
		box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
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
		color: var(--color-text-secondary);
	}

	.footer-text a {
		color: var(--color-primary);
		text-decoration: none;
		font-weight: 600;
		transition: color 0.2s;
	}

	.footer-text a:hover {
		color: var(--color-primary-hover);
		text-decoration: underline;
	}

	.free-forever {
		text-align: center;
		margin-top: 1rem;
		font-size: 0.8125rem;
		color: var(--color-text-tertiary);
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
</style>

<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';

	const API_URL = import.meta.env.VITE_API_URL || 'https://api.engagic.org';

	let selectedAmount: number | null = null;
	let customAmount = '';
	let loading = false;
	let errorMessage = '';
	let successMessage = '';
	let showSuccess = false;
	let showCanceled = false;

	const presetAmounts = [
		{ value: 500, label: '$5' },
		{ value: 1500, label: '$15' },
		{ value: 3000, label: '$30' },
		{ value: 5000, label: '$50' },
		{ value: 10000, label: '$100' }
	];

	onMount(() => {
		const urlParams = new URLSearchParams(window.location.search);
		showSuccess = urlParams.get('success') === 'true';
		showCanceled = urlParams.get('canceled') === 'true';

		if (showSuccess || showCanceled) {
			setTimeout(() => {
				showSuccess = false;
				showCanceled = false;
				window.history.replaceState({}, '', '/about/donate');
			}, 5000);
		}
	});

	function selectPresetAmount(amount: number) {
		selectedAmount = amount;
		customAmount = '';
		errorMessage = '';
	}

	function handleCustomAmountInput(event: Event) {
		const input = event.target as HTMLInputElement;
		const value = input.value.replace(/[^0-9.]/g, '');
		customAmount = value;

		if (value) {
			const dollars = parseFloat(value);
			if (!isNaN(dollars) && dollars >= 1) {
				selectedAmount = Math.round(dollars * 100);
				errorMessage = '';
			} else {
				selectedAmount = null;
			}
		} else {
			selectedAmount = null;
		}
	}

	async function handleDonate() {
		if (!selectedAmount) {
			errorMessage = 'Please select or enter an amount';
			return;
		}

		if (selectedAmount < 100) {
			errorMessage = 'Minimum donation is $1.00';
			return;
		}

		loading = true;
		errorMessage = '';

		try {
			const response = await fetch(`${API_URL}/api/donate/checkout`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({ amount: selectedAmount })
			});

			if (!response.ok) {
				const error = await response.json();
				throw new Error(error.detail || 'Failed to create checkout session');
			}

			const data = await response.json();

			if (data.checkout_url) {
				window.location.href = data.checkout_url;
			} else {
				throw new Error('No checkout URL received');
			}
		} catch (error) {
			errorMessage = error instanceof Error ? error.message : 'An unexpected error occurred';
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Support Engagic - Donations</title>
	<meta name="description" content="Support civic infrastructure that keeps democracy accessible" />
	<script src="https://liberapay.com/engagic/widgets/button.js"></script>
</svelte:head>

<article class="about-content">
	{#if showSuccess}
		<div class="alert alert-success">
			<h3>Thank you for your support!</h3>
			<p>Your donation helps keep civic infrastructure open and accessible. You should receive a receipt via email shortly.</p>
		</div>
	{/if}

	{#if showCanceled}
		<div class="alert alert-info">
			<p>Donation canceled. No charges were made. Feel free to try again when you're ready.</p>
		</div>
	{/if}

	<section class="section">
		<h1 class="section-heading">Support Open Civic Infrastructure</h1>
		<p>Engagic is free to use because democracy shouldn't have a paywall. But infrastructure costs money.</p>
		<p>We process thousands of government meetings, extract structured data, run AI summaries, and serve hundreds of thousands of API requests - all on donated resources.</p>
	</section>

	<section class="section highlight-section">
		<h2 class="section-heading">What Your Support Funds</h2>
		<div class="cost-list">
			<div class="cost-item">
				<span class="cost-label">Server Infrastructure</span>
				<span class="cost-detail">Processing pipeline, API hosting, database storage</span>
			</div>
			<div class="cost-item">
				<span class="cost-label">AI Processing Costs</span>
				<span class="cost-detail">Gemini API calls for meeting summarization</span>
			</div>
			<div class="cost-item">
				<span class="cost-label">Data Bandwidth</span>
				<span class="cost-detail">Fetching PDFs, serving API responses, CDN costs</span>
			</div>
			<div class="cost-item">
				<span class="cost-label">Development Time</span>
				<span class="cost-detail">New city adapters, feature improvements, maintenance</span>
			</div>
		</div>
	</section>

	<section class="section">
		<h2 class="section-heading">Ways to Support</h2>

		<div class="donation-options">
			<div class="donation-card">
				<h3 class="donation-heading">One-Time Donation</h3>
				<p>Help cover immediate infrastructure costs. Every dollar goes directly to keeping the platform running.</p>

				<div class="amount-selector">
					<div class="preset-amounts">
						{#each presetAmounts as preset}
							<button
								class="amount-button"
								class:selected={selectedAmount === preset.value}
								on:click={() => selectPresetAmount(preset.value)}
								disabled={loading}
							>
								{preset.label}
							</button>
						{/each}
					</div>

					<div class="custom-amount">
						<label for="custom-amount" class="custom-amount-label">Or enter custom amount:</label>
						<div class="custom-amount-input-wrapper">
							<span class="currency-symbol">$</span>
							<input
								id="custom-amount"
								type="text"
								placeholder="25.00"
								value={customAmount}
								on:input={handleCustomAmountInput}
								disabled={loading}
								class="custom-amount-input"
							/>
						</div>
					</div>

					{#if errorMessage}
						<div class="error-message">{errorMessage}</div>
					{/if}

					<button
						class="donate-button primary"
						on:click={handleDonate}
						disabled={!selectedAmount || loading}
					>
						{#if loading}
							Processing...
						{:else}
							Donate via Stripe
						{/if}
					</button>
				</div>
			</div>

			<div class="donation-card">
				<h3 class="donation-heading">Monthly Support</h3>
				<p>Sustainable funding helps us plan capacity and add more cities. Recurring support makes the biggest impact.</p>
				<div class="button-group">
					<div class="liberapay-wrapper">
						<noscript>
							<a href="https://liberapay.com/engagic/donate">
								<img alt="Donate using Liberapay" src="https://liberapay.com/assets/widgets/donate.svg" />
							</a>
						</noscript>
					</div>
				</div>
			</div>

			<div class="donation-card">
				<h3 class="donation-heading">Institutional Support</h3>
				<p>Universities, foundations, or civic organizations interested in supporting large-scale civic infrastructure.</p>
				<div class="button-group">
					<a href="mailto:billing@engagic.org" class="donate-button">
						Contact Us
					</a>
				</div>
			</div>
		</div>
	</section>

	<section class="section">
		<h2 class="section-heading">Other Ways to Help</h2>
		<div class="feature-list">
			<div class="feature-item">
				<h3 class="feature-heading">Contribute Code</h3>
				<p>We're open source (AGPL-3.0). Add city adapters, fix bugs, improve performance. <a href="https://github.com/Engagic/engagic" target="_blank" rel="noopener">Check out the repo</a>.</p>
			</div>
			<div class="feature-item">
				<h3 class="feature-heading">Spread the Word</h3>
				<p>Tell your local activists, journalists, and city council members. The more people use it, the more accountability we create.</p>
			</div>
			<div class="feature-item">
				<h3 class="feature-heading">Report Issues</h3>
				<p>Found a bug? Meeting data incorrect? <a href="https://github.com/Engagic/engagic/issues" target="_blank" rel="noopener">File an issue</a> and help us improve.</p>
			</div>
		</div>
	</section>

	<section class="section transparency-section">
		<h2 class="section-heading">Financial Transparency</h2>
		<p class="philosophy-lead">We believe in full transparency. Monthly cost breakdowns and sponsor acknowledgments coming soon.</p>
		<p>Current estimated monthly operating cost: <strong>$XXX/month</strong></p>
		<p>Current monthly support: <strong>$XXX/month</strong></p>
		<p class="contact-footer">
			Questions about where the money goes? <a href="mailto:billing@engagic.org">billing@engagic.org</a>
		</p>
	</section>
</article>

<style>
	.about-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-xl);
		padding-bottom: var(--space-xl);
		color: var(--text-primary);
	}

	.alert {
		padding: var(--space-lg);
		border-radius: var(--radius-md);
		margin-bottom: var(--space-lg);
	}

	.alert-success {
		background: var(--surface-secondary);
		border: 2px solid var(--civic-green);
	}

	.alert-success h3 {
		color: var(--civic-green);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		margin: 0 0 var(--space-sm) 0;
	}

	.alert-info {
		background: var(--surface-secondary);
		border: 2px solid var(--civic-blue);
	}

	.alert p {
		margin: 0;
	}

	.section {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.section-heading {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
		line-height: 1.2;
	}

	h1.section-heading {
		font-size: 2.5rem;
	}

	.about-content p {
		font-size: 1.1rem;
		line-height: 1.7;
		color: var(--text-primary);
		margin: 0;
	}

	.highlight-section {
		background: var(--surface-secondary);
		border: 2px solid var(--civic-blue);
		border-radius: var(--radius-lg);
		padding: var(--space-2xl);
		gap: var(--space-xl);
	}

	.transparency-section {
		background: var(--surface-secondary);
		border: 2px solid var(--civic-green);
		border-radius: var(--radius-lg);
		padding: var(--space-2xl);
		gap: var(--space-lg);
	}

	.cost-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.cost-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
		padding: var(--space-md);
		background: var(--surface-primary);
		border-radius: var(--radius-sm);
		border-left: 3px solid var(--civic-blue);
	}

	.cost-label {
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 600;
		font-size: 1.1rem;
		color: var(--text-primary);
	}

	.cost-detail {
		font-size: 1rem;
		color: var(--civic-gray);
		line-height: 1.6;
	}

	.donation-options {
		display: grid;
		gap: var(--space-lg);
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
	}

	.donation-card {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
		padding: var(--space-xl);
		background: var(--surface-primary);
		border: 2px solid var(--border-primary);
		border-radius: var(--radius-lg);
		transition: all var(--transition-normal);
	}

	.donation-card:hover {
		border-color: var(--civic-blue);
		box-shadow: 0 4px 16px var(--shadow-md);
	}

	.donation-heading {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin: 0;
	}

	.amount-selector {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
		margin-top: var(--space-sm);
	}

	.preset-amounts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(70px, 1fr));
		gap: var(--space-sm);
	}

	.amount-button {
		padding: var(--space-md);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		font-weight: 600;
		text-align: center;
		border-radius: var(--radius-md);
		border: 2px solid var(--border-primary);
		background: var(--surface-primary);
		color: var(--text-primary);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.amount-button:hover:not(:disabled) {
		border-color: var(--civic-blue);
		background: var(--civic-blue);
		color: var(--civic-white);
	}

	.amount-button.selected {
		background: var(--civic-blue);
		color: var(--civic-white);
		border-color: var(--civic-blue);
	}

	.amount-button:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.custom-amount {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.custom-amount-label {
		font-size: 0.95rem;
		color: var(--civic-gray);
		font-family: 'IBM Plex Mono', monospace;
	}

	.custom-amount-input-wrapper {
		position: relative;
		display: flex;
		align-items: center;
	}

	.currency-symbol {
		position: absolute;
		left: var(--space-md);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		color: var(--text-primary);
		pointer-events: none;
	}

	.custom-amount-input {
		width: 100%;
		padding: var(--space-md) var(--space-md) var(--space-md) var(--space-lg);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		border: 2px solid var(--border-primary);
		border-radius: var(--radius-md);
		background: var(--surface-primary);
		color: var(--text-primary);
		transition: border-color var(--transition-fast);
	}

	.custom-amount-input:focus {
		outline: none;
		border-color: var(--civic-blue);
	}

	.custom-amount-input:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.error-message {
		padding: var(--space-sm) var(--space-md);
		background: #fee;
		border: 1px solid #fcc;
		border-radius: var(--radius-sm);
		color: #c33;
		font-size: 0.9rem;
		font-family: 'IBM Plex Mono', monospace;
	}

	.button-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
		margin-top: var(--space-sm);
	}

	.liberapay-wrapper {
		display: flex;
		justify-content: center;
		padding: var(--space-md) 0;
	}

	.donate-button {
		display: inline-block;
		padding: var(--space-md) var(--space-lg);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		font-weight: 600;
		text-align: center;
		text-decoration: none;
		border-radius: var(--radius-md);
		border: 2px solid var(--border-primary);
		background: var(--surface-primary);
		color: var(--text-primary);
		transition: all var(--transition-fast);
		cursor: pointer;
	}

	.donate-button:hover:not(:disabled) {
		border-color: var(--civic-blue);
		background: var(--civic-blue);
		color: var(--civic-white);
		transform: translateY(-2px);
		box-shadow: 0 4px 12px var(--shadow-md);
	}

	.donate-button.primary {
		background: var(--civic-blue);
		color: var(--civic-white);
		border-color: var(--civic-blue);
	}

	.donate-button.primary:hover:not(:disabled) {
		background: var(--civic-accent);
		border-color: var(--civic-accent);
	}

	.donate-button:disabled {
		opacity: 0.6;
		cursor: not-allowed;
		transform: none;
	}

	.feature-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-lg);
		padding-left: var(--space-md);
		border-left: 2px solid var(--border-primary);
	}

	.feature-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.feature-heading {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin: 0;
	}

	.feature-item p {
		font-size: 1.1rem;
		line-height: 1.7;
	}

	.feature-item a {
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 600;
	}

	.feature-item a:hover {
		text-decoration: underline;
	}

	.philosophy-lead {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.15rem;
		font-weight: 500;
		color: var(--text-primary);
		line-height: 1.6;
	}

	.contact-footer {
		font-size: 1.1rem;
		line-height: 1.7;
		padding-top: var(--space-lg);
		border-top: 1px solid var(--border-primary);
	}

	.contact-footer a {
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 600;
		transition: color var(--transition-fast);
	}

	.contact-footer a:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}

	@media (max-width: 768px) {
		h1.section-heading {
			font-size: 2rem;
		}

		.section-heading {
			font-size: 1.5rem;
		}

		.about-content p {
			font-size: 1.05rem;
		}

		.highlight-section,
		.transparency-section {
			padding: var(--space-lg);
		}

		.donation-card {
			padding: var(--space-lg);
		}

		.donation-options {
			grid-template-columns: 1fr;
		}

		.preset-amounts {
			grid-template-columns: repeat(auto-fit, minmax(60px, 1fr));
		}
	}
</style>

<script lang="ts">
	import { onMount } from 'svelte';
	import SeoHead from '$lib/components/SeoHead.svelte';

	const API_URL = import.meta.env.VITE_API_URL || 'https://api.engagic.org';

	let donationType: 'one-time' | 'monthly' = 'one-time';
	let selectedAmount: number | null = null;
	let customAmount = '';
	let loading = false;
	let errorMessage = '';
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

		if (donationType === 'monthly') {
			// Liberapay: construct URL with custom amount
			const dollars = (selectedAmount / 100).toFixed(2);
			const liberapayUrl = `https://liberapay.com/engagic/donate?currency=USD&period=monthly&amount=${dollars}`;
			window.location.href = liberapayUrl;
			return;
		}

		// Stripe one-time donation
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

<SeoHead
	title="Donate - engagic"
	description="Support civic infrastructure that keeps democracy accessible"
	url="https://engagic.org/about/donate"
/>

<article class="about-content">
	{#if showSuccess}
		<div class="alert alert-success">
			<strong>Thank you for your generosity!</strong> Your donation helps keep civic infrastructure open and accessible.
		</div>
	{/if}

	{#if showCanceled}
		<div class="alert alert-info">
			Payment canceled. No charges were made.
		</div>
	{/if}

	<section class="section">
		<h1 class="section-heading">Donate</h1>
		<p>Democracy shouldn't have a paywall. Help us keep it free.</p>
		<div class="what-it-funds">
			<span>Server infrastructure</span>
			<span>AI processing</span>
			<span>Data bandwidth</span>
			<span>Development</span>
		</div>
	</section>

	<section class="section">
		<div class="donation-card">
			<div class="toggle-container">
				<button
					class="toggle-button"
					class:active={donationType === 'one-time'}
					on:click={() => { donationType = 'one-time'; errorMessage = ''; }}
				>
					One-Time
				</button>
				<button
					class="toggle-button"
					class:active={donationType === 'monthly'}
					on:click={() => { donationType = 'monthly'; errorMessage = ''; }}
				>
					Monthly
				</button>
			</div>

			{#if donationType === 'monthly'}
				<p class="card-subtitle">Sustainable funding makes the biggest impact</p>
			{:else}
				<p class="card-subtitle">Every dollar keeps democracy accessible</p>
			{/if}

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
				<div class="input-wrapper">
					<span class="currency">$</span>
					<input
						type="text"
						placeholder="Custom amount"
						value={customAmount}
						on:input={handleCustomAmountInput}
						disabled={loading}
					/>
				</div>
			</div>

			{#if errorMessage}
				<div class="error">{errorMessage}</div>
			{/if}

			<button
				class="donate-button"
				on:click={handleDonate}
				disabled={!selectedAmount || loading}
			>
				{#if loading}
					Processing...
				{:else if donationType === 'monthly'}
					Donate via Liberapay
				{:else}
					Donate via Stripe
				{/if}
			</button>
		</div>
	</section>

	<section class="section">
		<p class="contact-footer">
			Questions? <a href="mailto:billing@engagic.org">billing@engagic.org</a>
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

	.alert {
		padding: var(--space-md) var(--space-lg);
		border-radius: var(--radius-md);
		font-size: 1rem;
		text-align: center;
		margin-bottom: var(--space-md);
	}

	.alert-success {
		background: #e8f5e9;
		border: 2px solid var(--civic-green);
		color: #2e7d32;
	}

	.alert-info {
		background: var(--surface-secondary);
		border: 2px solid var(--civic-blue);
		color: var(--text-primary);
	}

	.what-it-funds {
		display: flex;
		gap: var(--space-lg);
		flex-wrap: wrap;
		font-size: 0.9rem;
		color: var(--civic-gray);
		font-family: 'IBM Plex Mono', monospace;
		padding-top: var(--space-xs);
	}

	.what-it-funds span {
		opacity: 0.7;
	}

	.donation-card {
		max-width: 600px;
		margin: 0 auto;
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: var(--space-lg);
		padding: var(--space-2xl);
		background: var(--surface-primary);
		border: 2px solid var(--border-primary);
		border-radius: var(--radius-lg);
		transition: all var(--transition-normal);
	}

	.donation-card:hover {
		border-color: var(--civic-blue);
		box-shadow: 0 4px 16px var(--shadow-md);
	}

	.toggle-container {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-sm);
		padding: 4px;
		background: var(--surface-secondary);
		border-radius: var(--radius-md);
	}

	.toggle-button {
		padding: var(--space-md);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		font-weight: 600;
		border-radius: var(--radius-sm);
		border: none;
		background: transparent;
		color: var(--text-secondary);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.toggle-button.active {
		background: var(--civic-blue);
		color: var(--civic-white);
	}

	.toggle-button:not(.active):hover {
		background: var(--surface-primary);
		color: var(--text-primary);
	}

	.card-subtitle {
		font-size: 0.95rem;
		color: var(--civic-gray);
		text-align: center;
		line-height: 1.4;
		margin-top: -var(--space-md);
	}

	.preset-amounts {
		display: grid;
		grid-template-columns: repeat(5, 1fr);
		gap: var(--space-sm);
	}

	.amount-button {
		padding: var(--space-md);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		font-weight: 600;
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
		opacity: 0.5;
		cursor: not-allowed;
	}

	.custom-amount {
		margin-top: -var(--space-sm);
	}

	.input-wrapper {
		position: relative;
	}

	.currency {
		position: absolute;
		left: var(--space-md);
		top: 50%;
		transform: translateY(-50%);
		font-family: 'IBM Plex Mono', monospace;
		color: var(--text-primary);
		pointer-events: none;
	}

	.custom-amount input {
		width: 100%;
		padding: var(--space-md) var(--space-md) var(--space-md) var(--space-xl);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		border: 2px solid var(--border-primary);
		border-radius: var(--radius-md);
		background: var(--surface-primary);
		color: var(--text-primary);
		transition: border-color var(--transition-fast);
	}

	.custom-amount input:focus {
		outline: none;
		border-color: var(--civic-blue);
	}

	.custom-amount input:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.error {
		padding: var(--space-sm) var(--space-md);
		background: #fee;
		border: 1px solid #fcc;
		border-radius: var(--radius-sm);
		color: #c33;
		font-size: 0.9rem;
		font-family: 'IBM Plex Mono', monospace;
		text-align: center;
		margin-top: -var(--space-sm);
	}

	.donate-button {
		width: 100%;
		padding: var(--space-lg);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.1rem;
		font-weight: 600;
		border-radius: var(--radius-md);
		border: none;
		background: var(--civic-blue);
		color: var(--civic-white);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.donate-button:hover:not(:disabled) {
		background: var(--civic-accent);
		transform: translateY(-2px);
		box-shadow: 0 4px 12px var(--shadow-md);
	}

	.donate-button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
		transform: none;
	}

	.contact-footer {
		font-size: 1.1rem;
		line-height: 1.7;
		padding-top: var(--space-lg);
		border-top: 1px solid var(--border-primary);
		text-align: center;
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

		.what-it-funds {
			font-size: 0.85rem;
			gap: var(--space-md);
		}

		.donation-card {
			padding: var(--space-xl);
		}

		.preset-amounts {
			grid-template-columns: repeat(3, 1fr);
		}
	}
</style>

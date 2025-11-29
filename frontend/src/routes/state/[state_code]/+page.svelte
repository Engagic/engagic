<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import StateMetrics from '$lib/components/StateMetrics.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const STATE_NAMES: Record<string, string> = {
		AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California',
		CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', FL: 'Florida', GA: 'Georgia',
		HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', IA: 'Iowa',
		KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland',
		MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri',
		MT: 'Montana', NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey',
		NM: 'New Mexico', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio',
		OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina',
		SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont',
		VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming'
	};

	const stateName = $derived(STATE_NAMES[data.stateCode] || data.stateCode);

	// Snapshot: Preserve scroll position during navigation
	export const snapshot = {
		capture: () => ({
			scrollY: typeof window !== 'undefined' ? window.scrollY : 0
		}),
		restore: (values: { scrollY: number }) => {
			if (typeof window !== 'undefined' && typeof values.scrollY === 'number') {
				setTimeout(() => window.scrollTo(0, values.scrollY), 0);
			}
		}
	};
</script>

<svelte:head>
	<title>{stateName} Legislative Intelligence - engagic</title>
	<meta name="description" content="Track legislative matters and civic activity across {stateName}" />
</svelte:head>

<div class="container">
	<a href="/" class="compact-logo">
		<img src="/icon-64.png" alt="engagic" class="logo-icon" />
	</a>

	<div class="state-header">
		<a href="/" class="back-link">← Back to search</a>
		<h1 class="state-title">{stateName}</h1>
	</div>

	<StateMetrics
		stateCode={data.stateCode}
		stateName={stateName}
		initialMetrics={data.metrics}
	/>

	<Footer />
</div>

<style>
	.container {
		width: var(--width-state);
		max-width: 100%;
		margin: 0 auto;
		padding: var(--space-xl) var(--space-md);
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		position: relative;
	}

	.compact-logo {
		position: absolute;
		top: 0;
		right: 1rem;
		z-index: 10;
		transition: transform var(--transition-fast);
	}

	.compact-logo:hover {
		transform: scale(1.05);
	}

	.logo-icon {
		width: 48px;
		height: 48px;
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-md);
	}

	.state-header {
		margin-bottom: var(--space-xl);
	}

	.back-link {
		display: inline-block;
		margin-bottom: var(--space-md);
		color: var(--color-action);
		text-decoration: none;
		font-family: var(--font-mono);
		font-weight: var(--font-medium);
		transition: color var(--transition-fast);
	}

	.back-link:hover {
		color: var(--color-action-hover);
		text-decoration: underline;
	}

	.state-title {
		font-family: var(--font-mono);
		font-size: var(--text-3xl);
		color: var(--text);
		margin: 0;
		font-weight: var(--font-semibold);
	}

	@media (max-width: 768px) {
		.container {
			padding: var(--space-lg) var(--space-md);
		}

		.logo-icon {
			width: 40px;
			height: 40px;
		}

		.state-title {
			font-size: var(--text-2xl);
		}
	}
</style>

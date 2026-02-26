<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import StateMetrics from '$lib/components/StateMetrics.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import SeoHead from '$lib/components/SeoHead.svelte';
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

<SeoHead
	title="{stateName} Legislative Intelligence - engagic"
	description="Track legislative matters and civic activity across {stateName}"
	url="https://engagic.org/state/{data.stateCode}"
/>

<div class="state-page">
	<div class="state-container">
		<div class="breadcrumb">
			<a href="/" class="breadcrumb-link">← Back to Search</a>
		</div>

		<StateMetrics
			stateCode={data.stateCode}
			stateName={stateName}
			initialMetrics={data.metrics}
			initialMeetings={data.meetings ?? undefined}
		/>
	</div>

	<Footer />
</div>

<style>
	.state-page {
		width: 100%;
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		padding: 2rem 1rem;
	}

	.state-container {
		width: 100%;
		max-width: 1400px;
		margin: 0 auto;
	}

	.breadcrumb {
		margin-bottom: 1.5rem;
	}

	.breadcrumb-link {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		color: var(--text-link);
		text-decoration: none;
		transition: color 0.2s ease;
		font-weight: 500;
	}

	.breadcrumb-link:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}

	@media (max-width: 768px) {
		.state-page {
			padding: 1rem 0.5rem;
		}
	}
</style>

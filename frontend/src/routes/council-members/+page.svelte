<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const citiesWithVotes = $derived(data.cities.filter(c => c.vote_count > 0).length);
	const citiesWithoutVotes = $derived(data.cities.length - citiesWithVotes);

	function formatNumber(num: number): string {
		if (num >= 1000000) {
			return (num / 1000000).toFixed(1) + 'M';
		} else if (num >= 1000) {
			return (num / 1000).toFixed(1) + 'K';
		}
		return num.toLocaleString();
	}

	function formatPop(num: number): string {
		if (num >= 1000000) {
			return (num / 1000000).toFixed(2) + 'M';
		} else if (num >= 1000) {
			return Math.round(num / 1000).toLocaleString() + 'K';
		}
		return num.toLocaleString();
	}
</script>

<svelte:head>
	<title>Council Members by City - Engagic</title>
	<meta name="description" content="View council member coverage across cities tracked by Engagic" />
	<link rel="canonical" href="https://engagic.org/council-members" />

	<!-- Open Graph -->
	<meta property="og:title" content="Council Members by City - engagic" />
	<meta property="og:description" content="View council member coverage across cities tracked by Engagic" />
	<meta property="og:type" content="website" />
	<meta property="og:url" content="https://engagic.org/council-members" />
	<meta property="og:image" content="https://engagic.org/icon-512.png" />
	<meta property="og:site_name" content="engagic" />

	<!-- Twitter -->
	<meta name="twitter:card" content="summary" />
	<meta name="twitter:title" content="Council Members by City - engagic" />
	<meta name="twitter:description" content="View council member coverage across cities tracked by Engagic" />
	<meta name="twitter:image" content="https://engagic.org/icon-512.png" />
</svelte:head>

<article class="page-container">
	<header class="page-header">
		<h1 class="primary-heading">Council Members by City</h1>
		<p class="section-desc">Cities with elected officials tracked, sorted by population. Click a city to view its council roster.</p>
	</header>

	<div class="stats-summary">
		<div class="summary-item">
			<span class="summary-count">{data.totals.cities_with_council_members}</span>
			<span class="summary-label">Cities</span>
		</div>
		<div class="summary-item">
			<span class="summary-count">{formatNumber(data.totals.total_council_members)}</span>
			<span class="summary-label">Council Members</span>
		</div>
		<div class="summary-item">
			<span class="summary-count">{formatNumber(data.totals.total_votes)}</span>
			<span class="summary-label">Votes Recorded</span>
		</div>
		<div class="summary-item summary-highlight">
			<span class="summary-count has-votes">{citiesWithVotes}</span>
			<span class="summary-label">with voting data</span>
		</div>
		<div class="summary-item">
			<span class="summary-count no-votes">{citiesWithoutVotes}</span>
			<span class="summary-label">without voting data</span>
		</div>
	</div>

	<div class="city-table-container">
		<table class="city-table">
			<thead>
				<tr>
					<th class="col-city">City</th>
					<th class="col-count">Members</th>
					<th class="col-votes">Voting Data</th>
					<th class="col-count">Committees</th>
					<th class="col-pop">Population</th>
				</tr>
			</thead>
			<tbody>
				{#each data.cities as city}
					<tr>
						<td class="col-city">
							<a href="/{city.banana}/council" class="city-link">
								{city.city_name}, {city.state}
							</a>
						</td>
						<td class="col-count">{city.council_member_count.toLocaleString()}</td>
						<td class="col-votes">
							{#if city.vote_count > 0}
								<span class="vote-badge vote-yes">{formatNumber(city.vote_count)} votes</span>
							{:else}
								<span class="vote-badge vote-no">No</span>
							{/if}
						</td>
						<td class="col-count">{city.committee_count.toLocaleString()}</td>
						<td class="col-pop">{formatPop(city.population)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</article>

<style>
	.page-container {
		display: flex;
		flex-direction: column;
		gap: var(--space-xl);
		padding: var(--space-xl) var(--space-lg);
		max-width: 1200px;
		margin: 0 auto;
		color: var(--text-primary);
	}

	.page-header {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.primary-heading {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
		line-height: 1.2;
	}

	.section-desc {
		font-size: 0.95rem;
		color: var(--text-secondary);
		margin: 0;
		line-height: 1.5;
	}

	.stats-summary {
		display: flex;
		gap: var(--space-2xl);
		flex-wrap: wrap;
	}

	.summary-item {
		display: flex;
		align-items: baseline;
		gap: var(--space-sm);
	}

	.summary-count {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--civic-blue);
	}

	.summary-label {
		font-size: 0.9rem;
		color: var(--text-secondary);
	}

	.summary-count.has-votes {
		color: rgb(22, 163, 74);
	}

	.summary-count.no-votes {
		color: var(--text-secondary);
	}

	.city-table-container {
		overflow-x: auto;
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-md);
		max-height: 700px;
		overflow-y: auto;
	}

	.city-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.9rem;
	}

	.city-table thead {
		position: sticky;
		top: 0;
		background: var(--surface-secondary);
		z-index: 1;
	}

	.city-table th {
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 600;
		text-align: left;
		padding: var(--space-md) var(--space-lg);
		border-bottom: 2px solid var(--border-primary);
		color: var(--text-secondary);
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.city-table td {
		padding: var(--space-md) var(--space-lg);
		border-bottom: 1px solid var(--border-subtle);
		color: var(--text-primary);
	}

	.city-table tbody tr:hover {
		background: var(--surface-secondary);
	}

	.col-city {
		min-width: 200px;
	}

	.city-link {
		color: var(--text-primary);
		text-decoration: none;
		font-weight: 500;
		transition: color var(--transition-fast);
	}

	.city-link:hover {
		color: var(--civic-blue);
	}

	.col-count {
		min-width: 80px;
		text-align: right;
		font-family: 'IBM Plex Mono', monospace;
	}

	.city-table th.col-count {
		text-align: right;
	}

	.col-votes {
		min-width: 120px;
		text-align: center;
	}

	.city-table th.col-votes {
		text-align: center;
	}

	.vote-badge {
		display: inline-block;
		padding: var(--space-xs) var(--space-sm);
		border-radius: var(--radius-sm);
		font-size: 0.8rem;
		font-weight: 500;
		font-family: 'IBM Plex Mono', monospace;
	}

	.vote-yes {
		background: rgba(34, 197, 94, 0.15);
		color: rgb(22, 163, 74);
	}

	.vote-no {
		background: rgba(168, 162, 158, 0.15);
		color: var(--text-secondary);
	}

	.col-pop {
		min-width: 100px;
		text-align: right;
		font-family: 'IBM Plex Mono', monospace;
	}

	.city-table th.col-pop {
		text-align: right;
	}

	@media (max-width: 768px) {
		.page-container {
			padding: var(--space-lg) var(--space-md);
			gap: var(--space-lg);
		}

		.primary-heading {
			font-size: 1.5rem;
		}

		.stats-summary {
			gap: var(--space-lg);
		}

		.summary-count {
			font-size: 1.25rem;
		}

		.city-table th,
		.city-table td {
			padding: var(--space-sm) var(--space-md);
		}

		.col-city {
			min-width: 150px;
		}

		.col-count {
			min-width: 60px;
		}
	}
</style>

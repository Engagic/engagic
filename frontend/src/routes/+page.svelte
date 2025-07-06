<script lang="ts">
	import { searchMeetings, processAgenda, type SearchResult, type Meeting, type ProcessResult } from '$lib/api';

	let searchQuery = $state('');
	let searchResults: SearchResult | null = $state(null);
	let selectedMeeting: Meeting | null = $state(null);
	let processingResult: ProcessResult | null = $state(null);
	let loading = $state(false);
	let processingMeeting = $state(false);
	let error = $state('');

	async function handleSearch() {
		if (!searchQuery.trim()) return;

		loading = true;
		error = '';
		searchResults = null;
		selectedMeeting = null;
		processingResult = null;

		try {
			const result = await searchMeetings(searchQuery.trim());
			searchResults = result;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Search failed';
		} finally {
			loading = false;
		}
	}

	async function handleMeetingClick(meeting: Meeting) {
		if (!searchResults?.city_slug) return;

		selectedMeeting = meeting;
		processingMeeting = true;
		processingResult = null;

		try {
			const result = await processAgenda(meeting, searchResults.city_slug);
			processingResult = result;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Processing failed';
		} finally {
			processingMeeting = false;
		}
	}

	function handleBack() {
		selectedMeeting = null;
		processingResult = null;
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			handleSearch();
		}
	}
</script>

<svelte:head>
	<title>engagic - civic engagement made simple</title>
	<meta name="description" content="Find your local government meetings and agendas" />
</svelte:head>

<div class="container">
	<header class="header">
		<a href="/" class="logo">engagic</a>
		<p class="tagline">civic engagement made simple</p>
	</header>

	<div class="search-section">
		<input 
			type="text" 
			class="search-input"
			bind:value={searchQuery}
			onkeydown={handleKeydown}
			placeholder="Enter zipcode or city, state (e.g. 94301 or Palo Alto, CA)"
			disabled={loading}
		/>
		<button 
			class="search-button" 
			onclick={handleSearch}
			disabled={loading || !searchQuery.trim()}
		>
			{loading ? 'Searching...' : 'Search'}
		</button>
	</div>

	{#if error}
		<div class="error-message">
			{error}
		</div>
	{/if}

	{#if selectedMeeting}
		<div class="meeting-detail">
			<button class="back-button" onclick={handleBack}>← Back to meetings</button>
			<h3>{selectedMeeting.title || selectedMeeting.meeting_name}</h3>
			<div class="meeting-date">
				{selectedMeeting.start || selectedMeeting.meeting_date}
			</div>
			
			{#if processingMeeting}
				<div class="processing-status">Processing agenda packet...</div>
			{/if}
			
			{#if processingResult}
				<div class="meeting-summary">
					{processingResult.summary}
				</div>
				<div class="processing-status">
					{processingResult.cached ? 'Cached result' : `Processed in ${processingResult.processing_time_seconds}s`}
				</div>
			{/if}
		</div>
	{:else if searchResults}
		<div class="results-section">
			{#if searchResults.success}
				{#if searchResults.city_name}
					<div class="city-info">
						<div class="city-name">{searchResults.city_name}, {searchResults.state}</div>
						{#if searchResults.cached}
							<div class="processing-status">Cached results</div>
						{/if}
					</div>
				{/if}

				{#if searchResults.meetings && searchResults.meetings.length > 0}
					<div class="meeting-list">
						{#each searchResults.meetings as meeting}
							<div class="meeting-card" onclick={() => handleMeetingClick(meeting)}>
								<div class="meeting-title">{meeting.title || meeting.meeting_name}</div>
								<div class="meeting-date">{meeting.start || meeting.meeting_date}</div>
								<div class="meeting-status">Click to view agenda summary</div>
							</div>
						{/each}
					</div>
				{:else}
					<div class="no-meetings">
						{searchResults.message || 'No meetings found'}
					</div>
				{/if}
			{:else}
				<div class="error-message">
					{searchResults.message || 'Search failed'}
				</div>
			{/if}
		</div>
	{:else if loading}
		<div class="loading">
			Searching for meetings...
		</div>
	{/if}
</div>
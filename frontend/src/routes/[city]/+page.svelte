<script lang="ts">
    import { page } from '$app/stores';
    import { onMount } from 'svelte';
    import { ApiService, type Meeting } from '$lib/api';

    let cityName = $state('');
    let meetings = $state<Meeting[]>([]);
    let isLoading = $state(true);
    let errorMessage = $state('');

    const formatMeetingDate = (dateString: string) => {
        const date = new Date(dateString);
        return {
            date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
            time: date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
        };
    };

    const isUpcoming = (dateString: string) => {
        const meetingDate = new Date(dateString);
        const now = new Date();
        return meetingDate >= now;
    };

    onMount(async () => {
        const city = $page.params.city;
        
        try {
            // For now, we'll get meetings by city slug
            // Later we could enhance this to load from a city API endpoint
            const cityMeetings = await ApiService.getMeetings(city);
            meetings = cityMeetings;
            cityName = city.replace(/([a-z])([A-Z])/g, '$1 $2'); // Add spaces between words
            cityName = cityName.charAt(0).toUpperCase() + cityName.slice(1); // Capitalize first letter
        } catch (error) {
            console.error('Error loading city data:', error);
            errorMessage = `Could not load meetings for ${city}`;
        } finally {
            isLoading = false;
        }
    });
</script>

<svelte:head>
    <title>Meetings in {cityName} - Engagic</title>
</svelte:head>

<div class="city-page">
    <div class="header">
        <h1>Meetings in {cityName}</h1>
        <a href="/" class="back-link">← Back to Search</a>
    </div>

    {#if isLoading}
        <div class="loading">
            <p>Loading meetings...</p>
        </div>
    {:else if errorMessage}
        <div class="error-message">
            <p>{errorMessage}</p>
        </div>
    {:else if meetings.length > 0}
        <div class="meetings-section">
            <h2>Upcoming Meetings</h2>
            <div class="meetings-list">
                {#each meetings as meeting}
                    {@const formatted = formatMeetingDate(meeting.start)}
                    {@const upcoming = isUpcoming(meeting.start)}
                    <div class="meeting-card" class:past={!upcoming}>
                        <div class="meeting-header">
                            <h3>{meeting.title}</h3>
                            <div class="meeting-meta">
                                <span class="date" class:upcoming={upcoming}>{formatted.date}</span>
                                <span class="time">{formatted.time}</span>
                            </div>
                        </div>
                        
                        <div class="meeting-actions">
                            <a href={meeting.packet_url} target="_blank" rel="noopener noreferrer" class="packet-link">
                                📄 View Meeting Packet
                            </a>
                        </div>
                        
                        {#if !upcoming}
                            <div class="past-notice">
                                This meeting has already occurred
                            </div>
                        {/if}
                    </div>
                {/each}
            </div>
        </div>
    {:else}
        <div class="no-meetings">
            <p>No meetings found for {cityName}</p>
            <p>This city may not have meetings available through our system yet.</p>
        </div>
    {/if}
</div>

<style>
    .city-page {
        max-width: 800px;
        margin: 0 auto;
        padding: 2rem;
    }

    .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 2rem;
        border-bottom: 2px solid var(--input-border);
        padding-bottom: 1rem;
    }

    .header h1 {
        margin: 0;
        color: var(--secondary);
        font-size: 2rem;
    }

    .back-link {
        color: var(--civic-blue);
        text-decoration: none;
        font-weight: 500;
        padding: 0.5rem 1rem;
        border: 1px solid var(--civic-blue);
        border-radius: 6px;
        transition: all 0.2s ease;
    }

    .back-link:hover {
        background: var(--civic-blue);
        color: white;
    }

    .loading, .error-message, .no-meetings {
        text-align: center;
        padding: 2rem;
        color: var(--gray);
    }

    .error-message {
        background: #fee2e2;
        border: 1px solid #fecaca;
        color: #dc2626;
        border-radius: 8px;
    }

    .meetings-section h2 {
        margin: 0 0 1.5rem 0;
        font-size: 1.5rem;
        color: var(--secondary);
    }

    .meetings-list {
        display: flex;
        flex-direction: column;
        gap: 1.5rem;
    }

    .meeting-card {
        background: var(--white);
        border: 1px solid var(--input-border);
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        transition: box-shadow 0.2s ease;
    }

    .meeting-card:hover {
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
    }

    .meeting-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 1rem;
    }

    .meeting-header h3 {
        margin: 0;
        font-size: 1.25rem;
        color: var(--secondary);
        font-weight: 600;
    }

    .meeting-meta {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        gap: 4px;
        text-align: right;
    }

    .date {
        font-weight: 600;
        color: var(--civic-blue);
    }

    .date.upcoming {
        color: var(--civic-green);
    }

    .time {
        font-size: 0.9rem;
        color: var(--gray);
    }

    .meeting-actions {
        margin-bottom: 1rem;
    }

    .packet-link {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        background: var(--civic-blue);
        color: white;
        text-decoration: none;
        border-radius: 8px;
        font-size: 0.9rem;
        font-weight: 500;
        transition: all 0.2s ease;
    }

    .packet-link:hover {
        background: var(--civic-blue-hover);
        transform: translateY(-1px);
    }

    .past-notice {
        background: var(--light-gray);
        color: var(--gray);
        padding: 0.5rem;
        border-radius: 6px;
        font-size: 0.9rem;
        text-align: center;
        font-style: italic;
    }

    .meeting-card.past {
        opacity: 0.7;
        border-color: var(--light-gray);
    }

    @media screen and (max-width: 640px) {
        .city-page {
            padding: 1rem;
        }

        .header {
            flex-direction: column;
            gap: 1rem;
            align-items: flex-start;
        }

        .header h1 {
            font-size: 1.5rem;
        }

        .meeting-header {
            flex-direction: column;
            gap: 0.5rem;
        }

        .meeting-meta {
            align-items: flex-start;
            text-align: left;
        }
    }
</style>
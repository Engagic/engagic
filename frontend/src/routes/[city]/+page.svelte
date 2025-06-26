<script lang="ts">
    import { page } from '$app/stores';
    import { onMount } from 'svelte';
    import { ApiService, type Meeting } from '$lib/api';

    let cityName = $state('');
    let meetings = $state<Meeting[]>([]);
    let isLoading = $state(true);
    let errorMessage = $state('');
    let isNewCity = $state(false);
    let needsManualConfig = $state(false);

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
            // Check if we have recent search result in localStorage
            const lastSearchResult = localStorage.getItem('lastSearchResult');
            if (lastSearchResult) {
                const result = JSON.parse(lastSearchResult);
                if (result.city_slug === city) {
                    meetings = result.meetings || [];
                    cityName = result.city;
                    isNewCity = result.is_new_city || false;
                    needsManualConfig = result.needs_manual_config || false;
                    isLoading = false;
                    return;
                }
            }
            
            // Fallback to API call
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

    {#if isNewCity}
        <div class="new-city-notice">
            <div class="notice-header">
                <div class="success-icon">✅</div>
                <h3>Welcome to engagic, {cityName}!</h3>
            </div>
            <div class="notice-content">
                <p><strong>Great news!</strong> We've successfully added your city to our system.</p>
                <div class="integration-status">
                    <h4>What happens next?</h4>
                    <ul>
                        <li>🔍 We're identifying your city's meeting websites</li>
                        <li>🤖 Setting up automated agenda processing</li>
                        <li>📅 You'll start seeing meetings here within 24-48 hours</li>
                    </ul>
                </div>
                <div class="help-text">
                    <p><strong>Want to help speed this up?</strong> Email us at <a href="mailto:hello@engagic.org">hello@engagic.org</a> with your city's meeting website URL.</p>
                </div>
            </div>
        </div>
    {/if}

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
                    {@const meetingDate = meeting.start || meeting.meeting_date || ''}
                    {@const formatted = formatMeetingDate(meetingDate)}
                    {@const upcoming = isUpcoming(meetingDate)}
                    <div class="meeting-card" class:past={!upcoming}>
                        <div class="meeting-header">
                            <h3>{meeting.title || meeting.meeting_name || 'Untitled Meeting'}</h3>
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
            {#if isNewCity}
                <div class="integration-pending">
                    <div class="pending-icon">⏳</div>
                    <h3>Integration in Progress</h3>
                    <p>We're working on connecting to {cityName}'s meeting system. This usually takes 24-48 hours.</p>
                    <div class="what-to-expect">
                        <h4>What to expect:</h4>
                        <ul>
                            <li>Upcoming city council meetings</li>
                            <li>Planning commission meetings</li>
                            <li>AI-generated agenda summaries</li>
                            <li>Direct links to meeting documents</li>
                        </ul>
                    </div>
                </div>
            {:else}
                <div class="no-data">
                    <div class="info-icon">ℹ️</div>
                    <h3>No Recent Meetings</h3>
                    <p>{cityName} may not have upcoming meetings scheduled, or we're still working on integrating their system.</p>
                    <p>Try checking back in a day or two, or <a href="mailto:hello@engagic.org">contact us</a> if you think this is an error.</p>
                </div>
            {/if}
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

    .loading, .error-message {
        text-align: center;
        padding: 2rem;
        color: var(--gray);
    }

    .no-meetings {
        padding: 2rem;
    }

    .integration-pending, .no-data {
        text-align: center;
        background: var(--white);
        border: 2px solid var(--input-border);
        border-radius: 12px;
        padding: 2rem;
    }

    .pending-icon, .info-icon {
        font-size: 3rem;
        margin-bottom: 1rem;
        display: block;
    }

    .integration-pending h3, .no-data h3 {
        margin: 0 0 1rem 0;
        color: var(--secondary);
        font-size: 1.5rem;
    }

    .integration-pending p, .no-data p {
        color: var(--gray);
        line-height: 1.6;
        margin-bottom: 1rem;
    }

    .what-to-expect {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1.5rem;
        margin-top: 1.5rem;
        text-align: left;
    }

    .what-to-expect h4 {
        margin: 0 0 1rem 0;
        color: var(--secondary);
        font-size: 1.1rem;
    }

    .what-to-expect ul {
        margin: 0;
        padding-left: 1.5rem;
        color: var(--gray);
    }

    .what-to-expect li {
        margin-bottom: 0.5rem;
        line-height: 1.4;
    }

    .no-data a {
        color: var(--civic-blue);
        text-decoration: none;
        font-weight: 500;
    }

    .no-data a:hover {
        text-decoration: underline;
    }

    .error-message {
        background: #fee2e2;
        border: 1px solid #fecaca;
        color: #dc2626;
        border-radius: 8px;
    }

    .new-city-notice {
        background: linear-gradient(135deg, #dcfce7 0%, #f0fdf4 100%);
        border: 2px solid var(--civic-green);
        border-radius: 12px;
        padding: 2rem;
        margin-bottom: 2rem;
    }

    .notice-header {
        display: flex;
        align-items: center;
        gap: 1rem;
        margin-bottom: 1.5rem;
    }

    .success-icon {
        font-size: 2rem;
    }

    .notice-header h3 {
        margin: 0;
        color: var(--civic-green);
        font-size: 1.5rem;
        font-weight: 600;
    }

    .notice-content {
        text-align: left;
    }

    .notice-content p {
        margin: 0 0 1rem 0;
        color: #166534;
        line-height: 1.6;
    }

    .integration-status {
        background: rgba(255, 255, 255, 0.7);
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }

    .integration-status h4 {
        margin: 0 0 0.75rem 0;
        color: #166534;
        font-size: 1rem;
    }

    .integration-status ul {
        margin: 0;
        padding-left: 1.5rem;
        color: #166534;
    }

    .integration-status li {
        margin-bottom: 0.5rem;
        line-height: 1.4;
    }

    .help-text {
        background: rgba(255, 255, 255, 0.5);
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid var(--civic-green);
    }

    .help-text p {
        margin: 0;
        font-size: 0.95rem;
    }

    .help-text a {
        color: var(--civic-blue);
        text-decoration: none;
        font-weight: 500;
    }

    .help-text a:hover {
        text-decoration: underline;
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
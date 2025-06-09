<script lang="ts">
    import { onMount } from 'svelte';
    import { ApiService, type RecentAgenda } from '$lib/api';

    let recentAgendas: RecentAgenda[] = $state([]);
    let isLoading = $state(true);
    let error = $state<string | null>(null);

    const cities = ['cityofpaloalto', 'mountain-view', 'san-francisco'];

    onMount(async () => {
        try {
            isLoading = true;
            error = null;
            
            // Fetch meetings from multiple cities
            const allMeetings: RecentAgenda[] = [];
            
            for (const city of cities) {
                try {
                    const meetings = await ApiService.getMeetings(city);
                    const formattedMeetings = meetings
                        .slice(0, 2) // Limit to 2 per city
                        .map(meeting => ApiService.formatMeetingAsAgenda(meeting, city));
                    allMeetings.push(...formattedMeetings);
                } catch (cityError) {
                    console.warn(`Failed to fetch meetings for ${city}:`, cityError);
                }
            }
            
            // Sort by date (most recent first) and limit total results
            recentAgendas = allMeetings
                .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
                .slice(0, 6);
                
        } catch (err) {
            error = err instanceof Error ? err.message : 'Failed to load recent agendas';
            console.error('Error loading recent agendas:', err);
        } finally {
            isLoading = false;
        }
    });
</script>

<div class="recent-agendas">
    <h3>Recent Agendas</h3>
    <div class="agenda-list">
        {#if isLoading}
            <div class="loading-state">
                <div class="loading-placeholder"></div>
                <div class="loading-placeholder"></div>
                <div class="loading-placeholder"></div>
            </div>
        {:else if error}
            <div class="error-state">
                <p>Unable to load recent agendas</p>
                <button onclick={() => window.location.reload()}>Retry</button>
            </div>
        {:else if recentAgendas.length === 0}
            <div class="empty-state">
                <p>No recent agendas available</p>
            </div>
        {:else}
            {#each recentAgendas as agenda}
                <a href={agenda.packet_url || `/agenda/${agenda.id}`} 
                   class="agenda-item" 
                   class:urgent={agenda.urgent}
                   target="_blank"
                   rel="noopener noreferrer">
                    <div class="agenda-header">
                        <div class="city-name">{agenda.city}</div>
                        <div class="agenda-date">{agenda.date}</div>
                    </div>
                    <div class="agenda-title">{agenda.title}</div>
                    <div class="agenda-summary">{agenda.summary}</div>
                    {#if agenda.urgent}
                        <div class="urgent-badge">Action Required</div>
                    {/if}
                </a>
            {/each}
        {/if}
    </div>
</div>

<style>
    .recent-agendas {
        width: 100%;
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
    }

    .recent-agendas h3 {
        font-size: 1.5rem;
        color: var(--secondary);
        margin-bottom: 20px;
        font-weight: 600;
        text-align: center;
    }

    .agenda-list {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        gap: 16px;
    }

    .agenda-item {
        display: block;
        padding: 20px;
        background: var(--white);
        border-radius: 12px;
        text-decoration: none;
        color: inherit;
        transition: all 0.2s ease;
        border: 1px solid var(--input-border);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
    }

    .agenda-item:hover {
        border-color: var(--civic-blue);
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    }

    .agenda-item.urgent {
        border-color: var(--civic-orange);
        background: linear-gradient(135deg, rgba(234, 88, 12, 0.02) 0%, rgba(255, 255, 255, 1) 100%);
    }

    .agenda-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
    }

    .city-name {
        font-size: 0.875rem;
        font-weight: 600;
        color: var(--civic-blue);
    }

    .agenda-date {
        font-size: 0.75rem;
        color: var(--gray);
        font-weight: 500;
    }

    .agenda-title {
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: 8px;
        line-height: 1.4;
        color: var(--secondary);
    }

    .agenda-summary {
        font-size: 0.875rem;
        color: var(--gray);
        line-height: 1.5;
    }

    .urgent-badge {
        font-size: 10px;
        background: var(--civic-orange);
        color: var(--white);
        padding: 2px 6px;
        border-radius: 4px;
        display: inline-block;
        margin-top: 6px;
        font-weight: 600;
    }

    .loading-state, .error-state, .empty-state {
        padding: 12px;
        text-align: center;
        color: var(--gray);
        font-size: 12px;
    }

    .loading-placeholder {
        height: 60px;
        background: var(--button);
        border-radius: var(--border-radius);
        margin-bottom: 6px;
        animation: pulse 1.5s ease-in-out infinite;
    }

    @keyframes pulse {
        0%, 100% { opacity: 0.6; }
        50% { opacity: 1; }
    }

    .error-state button {
        margin-top: 8px;
        padding: 4px 8px;
        font-size: 11px;
        background: var(--civic-blue);
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
    }

    .error-state button:hover {
        background: var(--civic-blue-hover, var(--civic-blue));
    }

    @media screen and (max-width: 768px) {
        .recent-agendas {
            display: none;
        }
    }
</style>
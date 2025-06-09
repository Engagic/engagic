<script lang="ts">
    import { browser } from "$app/environment";
    import IconSearch from "$components/icons/Search.svelte";

    let searchInput: HTMLInputElement;
    let zipcode = $state("");
    let isFocused = $state(false);
    let isLoading = $state(false);
    let searchResults = $state<any[]>([]);
    let hasSearched = $state(false);

    let validZipcode = $derived(zipcode.length === 5 && /^\d{5}$/.test(zipcode));
    let validCityName = $derived(zipcode.length > 2 && /^[a-zA-Z\s]+$/.test(zipcode));
    let searchable = $derived(validZipcode || validCityName);

    // Mock meeting data - replace with API call
    const mockMeetings = [
        {
            id: 1,
            title: "City Council Meeting",
            date: "2025-01-15",
            time: "7:00 PM",
            location: "City Hall, Council Chambers",
            agendaSummary: "Budget discussion for FY2025, housing development proposal on Main St, traffic safety improvements",
            topics: ["Budget", "Housing", "Transportation"]
        },
        {
            id: 2,
            title: "Planning Commission",
            date: "2025-01-18",
            time: "6:30 PM", 
            location: "Community Center",
            agendaSummary: "Review of new residential zoning proposal, environmental impact assessment for downtown development",
            topics: ["Zoning", "Environment", "Development"]
        },
        {
            id: 3,
            title: "Parks & Recreation Board",
            date: "2025-01-22",
            time: "5:30 PM",
            location: "Parks Department Office",
            agendaSummary: "Summer programs planning, playground renovation funding, community garden expansion proposal",
            topics: ["Parks", "Recreation", "Community"]
        }
    ];

    const searchByZipcode = async () => {
        if (!searchable || isLoading) return;
        
        isLoading = true;
        hasSearched = true;
        
        try {
            // Simulate API call
            await new Promise(resolve => setTimeout(resolve, 800));
            
            // Set mock results
            searchResults = mockMeetings;
            
            // Store search in localStorage
            if (browser) {
                localStorage.setItem('lastSearch', zipcode);
            }
            
        } catch (error) {
            console.error("Error searching:", error);
            searchResults = [];
        } finally {
            isLoading = false;
        }
    };

    const handleKeydown = (e: KeyboardEvent) => {
        if (!searchInput || isLoading) return;

        if (e.key === "Enter" && searchable && isFocused) {
            searchByZipcode();
        }

        if (["Escape", "Clear"].includes(e.key) && isFocused) {
            zipcode = "";
            searchResults = [];
            hasSearched = false;
        }
    };
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="search-container">
    <div class="input-container" class:focused={isFocused} class:valid={searchable}>
        <input
            bind:value={zipcode}
            bind:this={searchInput}
            oninput={() => (isFocused = true)}
            onfocus={() => (isFocused = true)}
            onblur={() => (isFocused = false)}
            type="text"
            placeholder="Enter zipcode or city name"
            disabled={isLoading}
        />

        {#if searchable}
            <button
                class="search-button"
                onclick={searchByZipcode}
                disabled={isLoading}
            >
                {#if isLoading}
                    Searching...
                {:else}
                    <IconSearch />
                    Search
                {/if}
            </button>
        {/if}
    </div>

    {#if hasSearched}
        <div class="results-section">
            {#if searchResults.length > 0}
                <h3>Upcoming Meetings</h3>
                <div class="meetings-list">
                    {#each searchResults as meeting}
                        <div class="meeting-card">
                            <div class="meeting-header">
                                <h4>{meeting.title}</h4>
                                <div class="meeting-meta">
                                    <span class="date">{new Date(meeting.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                                    <span class="time">{meeting.time}</span>
                                </div>
                            </div>
                            
                            <div class="meeting-location">
                                📍 {meeting.location}
                            </div>
                            
                            <div class="agenda-summary">
                                <h5>Agenda Summary:</h5>
                                <p>{meeting.agendaSummary}</p>
                            </div>
                            
                            <div class="topics">
                                {#each meeting.topics as topic}
                                    <span class="topic-tag">{topic}</span>
                                {/each}
                            </div>
                        </div>
                    {/each}
                </div>
            {:else}
                <div class="no-results">
                    <p>No upcoming meetings found for "{zipcode}"</p>
                    <p>Try searching for a different location.</p>
                </div>
            {/if}
        </div>
    {/if}
</div>

<style>
    .search-container {
        width: 100%;
        display: flex;
        flex-direction: column;
        gap: 2rem;
    }

    .input-container {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 16px 20px;
        background: var(--white);
        border: 2px solid var(--input-border);
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        transition: all 0.2s ease;
    }

    .input-container.focused {
        border-color: var(--civic-blue);
        box-shadow: 0 0 0 3px rgba(29, 78, 216, 0.1);
    }

    .input-container.valid {
        border-color: var(--civic-green);
    }

    input {
        flex: 1;
        border: none;
        outline: none;
        background: transparent;
        font-size: 1.125rem;
        color: var(--secondary);
    }

    input::placeholder {
        color: var(--gray);
    }

    .search-button {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px 20px;
        background: var(--civic-blue);
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .search-button:hover:not(:disabled) {
        background: var(--civic-blue-hover);
        transform: translateY(-1px);
    }

    .search-button:disabled {
        opacity: 0.6;
        cursor: not-allowed;
        transform: none;
    }

    .results-section {
        margin-top: 1rem;
    }

    .results-section h3 {
        margin: 0 0 1.5rem 0;
        font-size: 1.5rem;
        color: var(--secondary);
        text-align: center;
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

    .meeting-header h4 {
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

    .time {
        font-size: 0.9rem;
        color: var(--gray);
    }

    .meeting-location {
        color: var(--gray);
        margin-bottom: 1rem;
        font-size: 0.95rem;
    }

    .agenda-summary {
        margin-bottom: 1rem;
    }

    .agenda-summary h5 {
        margin: 0 0 0.5rem 0;
        font-size: 1rem;
        font-weight: 600;
        color: var(--secondary);
    }

    .agenda-summary p {
        margin: 0;
        color: var(--gray);
        line-height: 1.5;
    }

    .topics {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
    }

    .topic-tag {
        background: var(--light-gray);
        color: var(--gray);
        padding: 4px 10px;
        border-radius: 16px;
        font-size: 0.85rem;
        font-weight: 500;
    }

    .no-results {
        text-align: center;
        padding: 2rem;
        color: var(--gray);
    }

    .no-results p {
        margin: 0.5rem 0;
    }

    @media screen and (max-width: 640px) {
        .meeting-header {
            flex-direction: column;
            gap: 0.5rem;
        }

        .meeting-meta {
            align-items: flex-start;
            text-align: left;
        }

        .input-container {
            flex-direction: column;
            gap: 1rem;
        }

        .search-button {
            width: 100%;
            justify-content: center;
        }
    }
</style>
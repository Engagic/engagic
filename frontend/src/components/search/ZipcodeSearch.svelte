<script lang="ts">
    import { tick } from "svelte";
    import { browser } from "$app/environment";
    import SearchIcon from "$components/agenda/SearchIcon.svelte";
    import IconSearch from "$components/icons/Search.svelte";
    import IconLocation from "$components/icons/Location.svelte";
    import IconBookmark from "$components/icons/Bookmark.svelte";

    let searchInput: HTMLInputElement;
    let zipcode = $state("");
    let interests = $state<string[]>([]);
    let isFocused = $state(false);
    let isLoading = $state(false);
    let showInterests = $state(false);

    let validZipcode = $derived(zipcode.length === 5 && /^\d{5}$/.test(zipcode));
    let searchable = $derived(validZipcode);

    const interestOptions = [
        { id: 'housing', label: 'Housing & Development', icon: '🏠', color: 'var(--civic-blue)' },
        { id: 'transportation', label: 'Transportation', icon: '🚌', color: 'var(--civic-green)' },
        { id: 'environment', label: 'Environment', icon: '🌱', color: 'var(--civic-green)' },
        { id: 'budget', label: 'Budget & Finance', icon: '💰', color: 'var(--civic-gold)' },
        { id: 'safety', label: 'Public Safety', icon: '🚨', color: 'var(--civic-red)' },
        { id: 'parks', label: 'Parks & Recreation', icon: '🌳', color: 'var(--civic-green)' },
        { id: 'business', label: 'Business & Economy', icon: '🏢', color: 'var(--civic-purple)' },
        { id: 'education', label: 'Education', icon: '📚', color: 'var(--civic-blue)' }
    ];

    const toggleInterest = (interestId: string) => {
        if (interests.includes(interestId)) {
            interests = interests.filter(id => id !== interestId);
        } else {
            interests = [...interests, interestId];
        }
    };

    const searchByZipcode = async () => {
        if (!searchable || isLoading) return;
        
        isLoading = true;
        showInterests = true;
        
        try {
            // This would eventually integrate with your backend
            console.log('Searching for zipcode:', zipcode, 'with interests:', interests);
            // For now, just simulate the search
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            // Store user preferences in localStorage
            if (browser) {
                localStorage.setItem('userZipcode', zipcode);
                localStorage.setItem('userInterests', JSON.stringify(interests));
            }
            
        } catch (error) {
            console.error("Error searching by zipcode:", error);
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
            showInterests = false;
        }
    };

    // Load saved preferences
    if (browser) {
        const savedZipcode = localStorage.getItem('userZipcode');
        const savedInterests = localStorage.getItem('userInterests');
        
        if (savedZipcode) zipcode = savedZipcode;
        if (savedInterests) {
            try {
                interests = JSON.parse(savedInterests);
                if (interests.length > 0) showInterests = true;
            } catch (e) {
                interests = [];
            }
        }
    }
</script>

<svelte:window onkeydown={handleKeydown} />

<div id="zipcode-search" class="search-container">
    <div class="search-header">
        <div class="header-icon">
            <IconLocation />
        </div>
        <div class="header-text">
            <h2>Find Your Local Government</h2>
            <p>Enter your zipcode to discover meetings and decisions that affect your community</p>
        </div>
    </div>

    <div
        id="zipcode-input-container"
        class="input-container"
        class:focused={isFocused}
        class:searchable
        class:valid={validZipcode}
    >
        <SearchIcon loading={isLoading} />

        <input
            id="zipcode-input"
            bind:value={zipcode}
            bind:this={searchInput}
            oninput={() => (isFocused = true)}
            onfocus={() => (isFocused = true)}
            onblur={() => (isFocused = false)}
            type="text"
            inputmode="numeric"
            pattern="[0-9]*"
            maxlength="5"
            placeholder="Enter your zipcode (e.g., 94301)"
            disabled={isLoading}
        />

        {#if searchable}
            <button
                class="search-button"
                onclick={searchByZipcode}
                disabled={isLoading}
            >
                <IconSearch />
                Find My City
            </button>
        {/if}
    </div>

    {#if showInterests || interests.length > 0}
        <div class="interests-section" transition:slide>
            <div class="interests-header">
                <IconBookmark />
                <h3>What topics matter to you?</h3>
                <p>Get notified when these topics are discussed at local meetings</p>
            </div>
            
            <div class="interests-grid">
                {#each interestOptions as option}
                    <button
                        class="interest-chip"
                        class:selected={interests.includes(option.id)}
                        style="--interest-color: {option.color}"
                        onclick={() => toggleInterest(option.id)}
                    >
                        <span class="interest-icon">{option.icon}</span>
                        <span class="interest-label">{option.label}</span>
                    </button>
                {/each}
            </div>

            {#if interests.length > 0}
                <div class="selected-summary">
                    <p>You'll be notified about <strong>{interests.length}</strong> topic{interests.length !== 1 ? 's' : ''}</p>
                </div>
            {/if}
        </div>
    {/if}
</div>

<style>
    .search-container {
        display: flex;
        flex-direction: column;
        max-width: 680px;
        width: 100%;
        gap: 24px;
    }

    .search-header {
        display: flex;
        align-items: center;
        gap: 16px;
        text-align: left;
    }

    .header-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 48px;
        height: 48px;
        background: var(--civic-gradient);
        border-radius: 12px;
        flex-shrink: 0;
    }

    .header-icon :global(svg) {
        stroke: white;
        width: 24px;
        height: 24px;
    }

    .header-text h2 {
        margin: 0 0 8px 0;
        font-size: 1.5rem;
        font-weight: 600;
        color: var(--secondary);
    }

    .header-text p {
        margin: 0;
        color: var(--gray);
        font-size: 1rem;
        line-height: 1.5;
    }

    .input-container {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 16px 20px;
        background: var(--input-bg);
        border: 2px solid var(--input-border);
        border-radius: 16px;
        box-shadow: var(--input-shadow);
        transition: all 0.2s ease;
    }

    .input-container.focused {
        border-color: var(--input-border-focus);
        box-shadow: var(--input-shadow-focus);
    }

    .input-container.valid {
        border-color: var(--civic-green);
    }

    #zipcode-input {
        flex: 1;
        border: none;
        outline: none;
        background: transparent;
        font-size: 1.125rem;
        font-weight: 500;
        color: var(--secondary);
        letter-spacing: 0.05em;
    }

    #zipcode-input::placeholder {
        color: var(--gray);
        font-weight: 400;
    }

    .search-button {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px 20px;
        background: var(--civic-gradient);
        color: white;
        border: none;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.95rem;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 4px 12px rgba(29, 78, 216, 0.3);
    }

    .search-button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(29, 78, 216, 0.4);
    }

    .search-button:disabled {
        opacity: 0.6;
        cursor: not-allowed;
        transform: none;
    }

    .interests-section {
        padding: 24px;
        background: var(--light-gray);
        border-radius: 16px;
        border: 1px solid var(--input-border);
    }

    .interests-header {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        margin-bottom: 20px;
    }

    .interests-header :global(svg) {
        stroke: var(--civic-gold);
        width: 24px;
        height: 24px;
        margin-bottom: 8px;
    }

    .interests-header h3 {
        margin: 0 0 8px 0;
        font-size: 1.25rem;
        font-weight: 600;
        color: var(--secondary);
    }

    .interests-header p {
        margin: 0;
        color: var(--gray);
        font-size: 0.9rem;
    }

    .interests-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 12px;
        margin-bottom: 16px;
    }

    .interest-chip {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px 16px;
        background: var(--white);
        border: 2px solid var(--input-border);
        border-radius: 12px;
        cursor: pointer;
        transition: all 0.2s ease;
        font-size: 0.9rem;
        font-weight: 500;
    }

    .interest-chip:hover {
        border-color: var(--interest-color);
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }

    .interest-chip.selected {
        background: var(--interest-color);
        border-color: var(--interest-color);
        color: white;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }

    .interest-icon {
        font-size: 1.2rem;
    }

    .interest-label {
        white-space: nowrap;
    }

    .selected-summary {
        text-align: center;
        padding: 12px;
        background: var(--civic-gradient-success);
        color: white;
        border-radius: 8px;
        font-weight: 500;
    }

    .selected-summary p {
        margin: 0;
    }

    @media screen and (max-width: 640px) {
        .search-header {
            text-align: center;
            flex-direction: column;
        }

        .header-text h2 {
            font-size: 1.25rem;
        }

        .interests-grid {
            grid-template-columns: 1fr;
        }

        .interest-chip {
            justify-content: center;
        }
    }
</style>
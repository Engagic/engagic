<script lang="ts">
    import { tick } from "svelte";
    import { browser } from "$app/environment";
    import { ApiService } from "$lib/api";

    import SearchButton from "$components/agenda/buttons/SearchButton.svelte";
    import ClearButton from "$components/agenda/buttons/ClearButton.svelte";
    import Switcher from "$components/buttons/Switcher.svelte";
    import ActionButton from "$components/buttons/ActionButton.svelte";
    import SearchIcon from "$components/agenda/SearchIcon.svelte";

    import IconSearch from "$components/icons/Search.svelte";
    import IconLocation from "$components/icons/Location.svelte";
    import IconCalendar from "$components/icons/Calendar.svelte";

    let searchInput: HTMLInputElement;
    let searchQuery = $state("");
    let selectedCity = $state("cityofpaloalto");
    let searchMode = $state("recent"); // recent, city, url

    let isFocused = $state(false);
    let isLoading = $state(false);

    let searchable = $derived(searchQuery.trim().length > 0);
    let clearVisible = $derived(searchQuery && !isLoading);

    const processAgenda = async () => {
        if (!searchable || isLoading) return;
        
        isLoading = true;
        
        try {
            if (searchMode === "url") {
                // For URL mode, open the PDF directly
                if (searchQuery.includes("primegov.com") || searchQuery.includes(".pdf")) {
                    window.open(searchQuery, '_blank');
                } else {
                    throw new Error("Please enter a valid PDF URL");
                }
            } else {
                // For city/recent mode, fetch meetings and optionally filter
                const citySlug = selectedCity === "custom" ? "cityofpaloalto" : selectedCity;
                const meetings = await ApiService.getMeetings(citySlug);
                
                if (meetings.length > 0) {
                    // If there's a search query, try to find matching meeting
                    if (searchQuery.trim()) {
                        const matchingMeeting = meetings.find(meeting => 
                            meeting.title.toLowerCase().includes(searchQuery.toLowerCase())
                        );
                        if (matchingMeeting) {
                            window.open(matchingMeeting.packet_url, '_blank');
                        } else {
                            // Open the most recent meeting if no match found
                            window.open(meetings[0].packet_url, '_blank');
                        }
                    } else {
                        // Open most recent meeting
                        window.open(meetings[0].packet_url, '_blank');
                    }
                } else {
                    throw new Error("No meetings found for the selected city");
                }
            }
        } catch (error) {
            console.error("Error processing agenda:", error);
            alert(error instanceof Error ? error.message : "Failed to process agenda");
        } finally {
            isLoading = false;
        }
    };

    const handleKeydown = (e: KeyboardEvent) => {
        if (!searchInput || isLoading) return;

        if (e.metaKey || e.ctrlKey || e.key === "/") {
            searchInput.focus();
        }

        if (e.key === "Enter" && searchable && isFocused) {
            processAgenda();
        }

        if (["Escape", "Clear"].includes(e.key) && isFocused) {
            searchQuery = "";
        }
    };

    const cityOptions = [
        { value: "cityofpaloalto", label: "Palo Alto" },
        { value: "mountain-view", label: "Mountain View" },
        { value: "san-francisco", label: "San Francisco" },
        { value: "custom", label: "Custom URL" }
    ];
</script>

<svelte:window onkeydown={handleKeydown} />

<div id="agenda-search-box">
    <div
        id="input-container"
        class:focused={isFocused}
        class:searchable
        class:clear-visible={clearVisible}
    >
        <SearchIcon loading={isLoading} />

        <input
            id="search-area"
            bind:value={searchQuery}
            bind:this={searchInput}
            oninput={() => (isFocused = true)}
            onfocus={() => (isFocused = true)}
            onblur={() => (isFocused = false)}
            spellcheck="false"
            autocomplete="off"
            autocapitalize="off"
            maxlength="512"
            placeholder={searchMode === "url" 
                ? "Paste agenda PDF URL..." 
                : "Search for agenda topics, dates, or items..."}
            disabled={isLoading}
        />

        <ClearButton click={() => (searchQuery = "")} />
        <SearchButton
            query={searchQuery}
            city={selectedCity}
            mode={searchMode}
            bind:loading={isLoading}
            onClick={processAgenda}
        />
    </div>

    <div id="action-container">
        <Switcher>
            <button
                class="button"
                class:active={searchMode === "recent"}
                onclick={() => searchMode = "recent"}
            >
                <IconCalendar />
                Recent Agendas
            </button>
            <button
                class="button"
                class:active={searchMode === "city"}
                onclick={() => searchMode = "city"}
            >
                <IconLocation />
                By City
            </button>
            <button
                class="button"
                class:active={searchMode === "url"}
                onclick={() => searchMode = "url"}
            >
                <IconSearch />
                Custom URL
            </button>
        </Switcher>

        {#if searchMode === "city"}
            <select 
                bind:value={selectedCity}
                class="city-selector"
            >
                {#each cityOptions as option}
                    <option value={option.value}>{option.label}</option>
                {/each}
            </select>
        {/if}
    </div>
</div>

<style>
    #agenda-search-box {
        display: flex;
        flex-direction: column;
        max-width: 640px;
        width: 100%;
        gap: 6px;
        position: relative;
    }

    #input-container {
        --input-padding: 10px;
        display: flex;
        box-shadow: 0 0 0 1.5px var(--input-border) inset;
        outline: 1.5px solid var(--input-border);
        outline-offset: -1.5px;
        border-radius: var(--border-radius);
        align-items: center;
        gap: var(--input-padding);
        font-size: 14px;
        flex: 1;
    }

    #input-container:not(.clear-visible) :global(#clear-button) {
        display: none;
    }

    #input-container:not(.searchable) :global(#search-button) {
        display: none;
    }

    #input-container.clear-visible {
        padding-right: var(--input-padding);
    }

    #input-container.searchable {
        padding-right: 0;
    }

    #input-container.focused {
        box-shadow: none;
        outline: var(--civic-blue) 2px solid;
        outline-offset: -1px;
    }

    #input-container.focused :global(#search-icons svg) {
        stroke: var(--civic-blue);
    }

    #input-container.searchable :global(#search-icons svg) {
        stroke: var(--civic-blue);
    }

    #search-area {
        display: flex;
        width: 100%;
        margin: 0;
        padding: var(--input-padding) 0;
        padding-left: calc(var(--input-padding) + 28px);
        height: 18px;
        align-items: center;
        border: none;
        outline: none;
        background-color: transparent;
        color: var(--secondary);
        -webkit-tap-highlight-color: transparent;
        flex: 1;
        font-weight: 500;
        font-size: inherit;
        border-radius: var(--border-radius);
    }

    #search-area::placeholder {
        color: var(--gray);
        opacity: 1;
    }

    input:disabled {
        opacity: 1;
    }

    #action-container {
        display: flex;
        flex-direction: row;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
    }

    .city-selector {
        padding: 6px 12px;
        border-radius: var(--border-radius);
        border: 1px solid var(--input-border);
        background-color: var(--button);
        color: var(--button-text);
        font-size: 14px;
        cursor: pointer;
    }

    .city-selector:focus {
        outline: var(--focus-ring);
        outline-offset: var(--focus-ring-offset);
    }

    @media screen and (max-width: 440px) {
        #action-container {
            flex-direction: column;
            gap: 5px;
        }

        #action-container :global(.button) {
            width: 100%;
        }

        .city-selector {
            width: 100%;
        }
    }
</style>
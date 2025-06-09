<script lang="ts">
    import { browser } from "$app/environment";
    import { goto } from "$app/navigation";
    import IconSearch from "$components/icons/Search.svelte";
    import { ApiService, type Meeting } from "$lib/api";

    let searchInput: HTMLInputElement;
    let searchQuery = $state("");
    let isFocused = $state(false);
    let isLoading = $state(false);
    let errorMessage = $state("");

    let validZipcode = $derived(searchQuery.length === 5 && /^\d{5}$/.test(searchQuery));
    let searchable = $derived(validZipcode);

    const searchByZipcode = async () => {
        if (!searchable || isLoading) return;
        
        isLoading = true;
        errorMessage = "";
        
        try {
            const result = await ApiService.searchMeetings(searchQuery);
            
            // Store search in localStorage
            if (browser) {
                localStorage.setItem('lastSearch', searchQuery);
            }
            
            // Redirect to city page
            goto(`/${result.city_slug}`);
            
        } catch (error) {
            console.error("Error searching:", error);
            errorMessage = error instanceof Error ? error.message : "Failed to search meetings";
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
            searchQuery = "";
            errorMessage = "";
        }
    };
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="search-container">
    <div class="input-container" class:focused={isFocused} class:valid={searchable}>
        <input
            bind:value={searchQuery}
            bind:this={searchInput}
            oninput={() => (isFocused = true)}
            onfocus={() => (isFocused = true)}
            onblur={() => (isFocused = false)}
            type="text"
            placeholder="Enter zipcode"
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

    {#if errorMessage}
        <div class="error-message">
            <p>{errorMessage}</p>
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


    .error-message {
        background: #fee2e2;
        border: 1px solid #fecaca;
        color: #dc2626;
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
    }

    .error-message p {
        margin: 0;
    }

    @media screen and (max-width: 640px) {
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
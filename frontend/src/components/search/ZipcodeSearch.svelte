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
    let successMessage = $state("");

    let validZipcode = $derived(searchQuery.length === 5 && /^\d{5}$/.test(searchQuery));
    let validCityName = $derived(searchQuery.length >= 2 && /^[a-zA-Z\s-'.,]+$/.test(searchQuery));
    let searchable = $derived(validZipcode || validCityName);
    
    function getInputHint(query: string, isValidZip: boolean, isValidCity: boolean): string {
        if (query.length === 0) return "";
        if (query.length > 0 && query.length < 2) return "Enter at least 2 characters";
        if (query.length > 2 && query.length < 5 && /^\d+$/.test(query)) return "Enter full 5-digit zipcode";
        if (query.length === 5 && !/^\d{5}$/.test(query)) return "Zipcode must be 5 digits";
        if (query.length >= 2 && !/^[a-zA-Z\s-'.,\d]+$/.test(query)) return "Please use only letters, numbers, spaces, and basic punctuation";
        if (isValidZip) return "Valid zipcode ✓";
        if (isValidCity) return "Valid city name ✓";
        return "";
    }
    
    let inputHint = $derived(getInputHint(searchQuery, validZipcode, validCityName));

    const performSearch = async () => {
        if (!searchable || isLoading) return;
        
        isLoading = true;
        errorMessage = "";
        successMessage = "";
        
        try {
            console.log('Starting search for:', searchQuery);
            const result = await ApiService.searchMeetings(searchQuery);
            console.log('Search result received:', result);
            
            // Validate we got a proper response
            if (!result || !result.city_slug) {
                throw new Error('Invalid response from server');
            }
            
            // Store search in localStorage
            if (browser) {
                localStorage.setItem('lastSearch', searchQuery);
                localStorage.setItem('lastSearchResult', JSON.stringify(result));
            }
            
            // Show success message for new cities before redirecting
            if (result.is_new_city) {
                successMessage = `Great! We've added ${result.city} to our system.`;
                console.log('New city registered:', result.city);
                // Brief delay to show success message
                setTimeout(() => {
                    goto(`/${result.city_slug}`);
                }, 1500);
            } else {
                console.log('Existing city found:', result.city);
                // Existing city - redirect immediately
                goto(`/${result.city_slug}`);
            }
            
        } catch (error) {
            console.error("Search failed:", error);
            console.error("Error details:", {
                message: error instanceof Error ? error.message : 'Unknown error',
                stack: error instanceof Error ? error.stack : 'No stack trace',
                searchQuery,
                validZipcode,
                validCityName
            });
            
            // Handle different error types
            if (error instanceof Error) {
                const errorMsg = error.message.toLowerCase();
                
                if (errorMsg.includes('timeout') || errorMsg.includes('abort')) {
                    errorMessage = "Search timed out. Please try again.";
                } else if (errorMsg.includes('network') || errorMsg.includes('failed to fetch')) {
                    errorMessage = "Connection failed. Please check your internet and try again.";
                } else if (errorMsg.includes('not found') || errorMsg.includes('404')) {
                    if (validZipcode) {
                        errorMessage = "That zipcode wasn't found. Please check and try again.";
                    } else {
                        errorMessage = "That city wasn't found. Try a different spelling or nearby city.";
                    }
                } else if (errorMsg.includes('invalid response')) {
                    errorMessage = "Server returned invalid data. Please try again.";
                } else {
                    errorMessage = `Search error: ${error.message}`;
                }
            } else {
                errorMessage = "Something went wrong. Please try again in a moment.";
            }
        } finally {
            isLoading = false;
        }
    };


    const handleKeydown = (e: KeyboardEvent) => {
        if (!searchInput || isLoading) return;

        if (e.key === "Enter" && searchable && isFocused) {
            performSearch();
        }

        if (["Escape", "Clear"].includes(e.key) && isFocused) {
            searchQuery = "";
            errorMessage = "";
            successMessage = "";
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
            placeholder="Enter zipcode (12345) or city name"
            disabled={isLoading}
        />

        {#if searchable}
            <button
                class="search-button"
                onclick={performSearch}
                disabled={isLoading}
            >
                {#if isLoading}
                    <div class="loading-spinner"></div>
                    Searching...
                {:else}
                    <IconSearch />
                    Search
                {/if}
            </button>
        {/if}
    </div>
    
    {#if inputHint && !isLoading}
        <div class="input-hint" class:valid={searchable} class:invalid={!searchable && searchQuery.length > 0}>
            {inputHint}
        </div>
    {/if}

    {#if successMessage}
        <div class="success-message">
            <p>{successMessage}</p>
            <div class="loading-dots">Loading your city page...</div>
        </div>
    {:else if errorMessage}
        <div class="error-message">
            <p>{errorMessage}</p>
            <button class="retry-button" onclick={() => { errorMessage = ''; performSearch(); }}>Try Again</button>
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


    .loading-spinner {
        width: 16px;
        height: 16px;
        border: 2px solid rgba(255, 255, 255, 0.3);
        border-top: 2px solid white;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    .success-message {
        background: linear-gradient(135deg, #dcfce7 0%, #f0fdf4 100%);
        border: 2px solid var(--civic-green);
        color: #166534;
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
    }

    .success-message p {
        margin: 0 0 0.5rem 0;
        font-weight: 600;
    }

    .loading-dots {
        font-size: 0.9rem;
        opacity: 0.8;
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
        margin: 0 0 0.75rem 0;
    }

    .retry-button {
        background: var(--civic-blue);
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 6px;
        font-size: 0.9rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .retry-button:hover {
        background: var(--civic-blue-hover);
        transform: translateY(-1px);
    }

    .input-hint {
        font-size: 0.875rem;
        padding: 0.5rem 0;
        text-align: center;
        transition: all 0.2s ease;
    }

    .input-hint.valid {
        color: var(--civic-green);
        font-weight: 500;
    }

    .input-hint.invalid {
        color: #dc2626;
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
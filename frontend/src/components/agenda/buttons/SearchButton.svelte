<script lang="ts">
    export let query: string;
    export let city: string;
    export let mode: string;
    export let loading: boolean = false;
    export let onClick: () => void;

    $: disabled = !query.trim() || loading;
</script>

<button
    id="search-button"
    class="button"
    class:active={!disabled}
    {disabled}
    on:click={onClick}
>
    {#if loading}
        <div class="spinner">⟳</div>
    {:else}
        🔍
    {/if}
    Search
</button>

<style>
    #search-button {
        background-color: var(--civic-blue);
        color: var(--white);
        border-radius: 0 var(--border-radius) var(--border-radius) 0;
        padding: 10px 16px;
        font-weight: 600;
        border: none;
        cursor: pointer;
        transition: all 0.15s;
    }

    #search-button:hover:not(:disabled) {
        background-color: var(--civic-blue);
        filter: brightness(1.1);
    }

    #search-button:active:not(:disabled) {
        filter: brightness(0.95);
    }

    #search-button:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .spinner {
        animation: spin 1s linear infinite;
        display: inline-block;
    }

    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
</style>
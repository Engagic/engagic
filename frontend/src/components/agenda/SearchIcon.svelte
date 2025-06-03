<script lang="ts">
    export let loading: boolean = false;
</script>

<div id="search-icons">
    {#if loading}
        <div class="spinner">
            <svg width="18" height="18" viewBox="0 0 24 24">
                <circle 
                    cx="12" 
                    cy="12" 
                    r="10" 
                    fill="none" 
                    stroke="currentColor" 
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-dasharray="15.71 15.71"
                    stroke-dashoffset="15.71"
                >
                    <animateTransform
                        attributeName="transform"
                        attributeType="XML"
                        type="rotate"
                        dur="1s"
                        from="0 12 12"
                        to="360 12 12"
                        repeatCount="indefinite"/>
                </circle>
            </svg>
        </div>
    {:else}
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.35-4.35"/>
        </svg>
    {/if}
</div>

<style>
    #search-icons {
        position: absolute;
        left: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: var(--gray);
        transition: color 0.15s;
    }

    .spinner {
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
</style>
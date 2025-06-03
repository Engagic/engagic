<script lang="ts">
    export let click: () => void;
</script>

<button
    id="clear-button"
    class="button"
    on:click={click}
    aria-label="Clear search"
>
    ✕
</button>

<style>
    #clear-button {
        background: none;
        border: none;
        color: var(--gray);
        cursor: pointer;
        padding: 4px;
        border-radius: 50%;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 12px;
        transition: all 0.15s;
        box-shadow: none;
    }

    #clear-button:hover {
        background-color: var(--button-hover-transparent);
        color: var(--secondary);
    }

    #clear-button:active {
        background-color: var(--button-press-transparent);
    }
</style>
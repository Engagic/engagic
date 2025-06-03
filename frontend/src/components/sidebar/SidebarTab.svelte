<script lang="ts">
    import { page } from "$app/stores";
    
    export let name: string;
    export let path: string;
    export let icon: any;
    export let beta: boolean = false;

    $: isActive = $page.url.pathname === path || 
        ($page.url.pathname.startsWith(path) && path !== "/");
</script>

<a
    href={path}
    class="sidebar-tab"
    class:active={isActive}
    aria-label={name}
    role="tab"
    aria-selected={isActive}
>
    <div class="tab-icon">
        <svelte:component this={icon} size={20} />
    </div>
    <div class="tab-text">
        {name}
        {#if beta}
            <span class="beta-label">beta</span>
        {/if}
    </div>
</a>

<style>
    .sidebar-tab {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-decoration: none;
        color: var(--gray);
        padding: var(--sidebar-tab-padding);
        border-radius: var(--border-radius);
        transition: all 0.15s;
        gap: 4px;
        position: relative;
        z-index: 2;
    }

    .sidebar-tab:hover {
        background-color: var(--button-hover-transparent);
        color: var(--sidebar-highlight);
    }

    .sidebar-tab.active {
        background-color: var(--secondary);
        color: var(--primary);
    }

    .sidebar-tab.active:hover {
        background-color: var(--button-active-hover);
    }

    .tab-icon {
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .tab-text {
        font-size: var(--sidebar-font-size);
        font-weight: 500;
        text-align: center;
        line-height: 1.2;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1px;
    }

    .beta-label {
        font-size: 9px;
        color: var(--civic-orange);
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .sidebar-tab.active .beta-label {
        color: var(--primary);
        opacity: 0.8;
    }

    @media screen and (max-width: 535px) {
        .sidebar-tab {
            flex-direction: row;
            gap: 6px;
            padding: 8px 12px;
            margin: 0 2px;
        }

        .tab-text {
            font-size: 12px;
        }

        .tab-icon {
            flex-shrink: 0;
        }

        .beta-label {
            position: absolute;
            top: -2px;
            right: -8px;
            font-size: 8px;
        }
    }
</style>
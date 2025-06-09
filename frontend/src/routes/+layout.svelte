<script lang="ts">
    import "../app.css";

    import { onMount } from "svelte";
    import { page } from "$app/stores";
    import { browser } from "$app/environment";
    import { afterNavigate } from "$app/navigation";

    import { device } from "$lib/device";
    import currentTheme from "$lib/state/theme.ts";

    import Sidebar from "$components/sidebar/Sidebar.svelte";
    import DialogHolder from "$components/dialog/DialogHolder.svelte";

    $: reduceMotion = device.prefers.reducedMotion;
    $: reduceTransparency = device.prefers.reducedTransparency;

    afterNavigate(async () => {
        const to_focus: HTMLElement | null =
            document.querySelector("[data-first-focus]");
        to_focus?.focus();
    });

    onMount(() => {
        // Initialize any needed startup logic
    });
</script>

<svelte:head>
    <title>engagic - Civic Engagement Made Simple</title>
    <meta name="description" content="Stay informed about local government decisions that affect your community" />
    <meta property="og:description" content="Stay informed about local government decisions that affect your community" />
</svelte:head>

<div
    style="display: contents"
    data-theme={browser ? $currentTheme : undefined}
>
    <div
        id="engagic"
        class:loaded={browser}
        data-mobile={device.is.mobile}
        data-reduce-motion={reduceMotion}
        data-reduce-transparency={reduceTransparency}
    >
        <DialogHolder />
        <Sidebar />
        <div id="content">
            <slot></slot>
        </div>
    </div>
</div>

<style>
    #engagic {
        height: 100%;
        width: 100%;
        display: grid;
        grid-template-columns:
            calc(var(--sidebar-width) + var(--sidebar-inner-padding) * 2)
            1fr;
        overflow: hidden;
        background-color: var(--sidebar-bg);
        color: var(--secondary);
        position: fixed;
    }

    #content {
        display: flex;
        overflow: scroll;
        background-color: var(--primary);
        box-shadow: 0 0 0 var(--content-border-thickness) var(--content-border);
        margin-left: var(--content-border-thickness);
    }

    @media (display-mode: standalone) and (min-width: 535px)  {
        [data-mobile="false"] #content {
            margin-top: var(--content-border-thickness);
            border-top-left-radius: 8px;
        }
    }

    @media screen and (max-width: 535px) {
        #engagic {
            display: grid;
            grid-template-columns: unset;
            grid-template-rows:
                1fr
                calc(
                    var(--sidebar-height-mobile) + var(--sidebar-inner-padding) * 2
                );
        }

        #content {
            padding-top: env(safe-area-inset-top);
            order: -1;
            margin: 0;
            box-shadow: none;
            border-bottom-left-radius: calc(var(--border-radius) * 2);
            border-bottom-right-radius: calc(var(--border-radius) * 2);
        }
    }
</style>
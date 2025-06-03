<script lang="ts">
    import EngageMintIcon from "$components/sidebar/EngageMintIcon.svelte";
    import SidebarTab from "$components/sidebar/SidebarTab.svelte";

    import IconHome from "$components/icons/Home.svelte";
    import IconSearch from "$components/icons/Search.svelte";
    import IconCalendar from "$components/icons/Calendar.svelte";
    import IconSettings from "$components/icons/Settings.svelte";
    import IconInfo from "$components/icons/Info.svelte";
    import IconBookmark from "$components/icons/Bookmark.svelte";

    let screenWidth: number;
</script>

<svelte:window bind:innerWidth={screenWidth} />

<nav id="sidebar" aria-label="Main navigation">
    <EngageMintIcon />
    <div id="sidebar-tabs" role="tablist">
        <div id="sidebar-actions" class="sidebar-inner-container">
            <SidebarTab name="home" path="/" icon={IconHome} />
            <SidebarTab name="search" path="/search" icon={IconSearch} />
            <SidebarTab name="meetings" path="/meetings" icon={IconCalendar} />
            <SidebarTab name="bookmarks" path="/bookmarks" icon={IconBookmark} />
        </div>
        <div id="sidebar-info" class="sidebar-inner-container">
            <SidebarTab name="settings" path="/settings" icon={IconSettings} />
            <SidebarTab name="about" path="/about" icon={IconInfo} />
        </div>
    </div>
</nav>

<style>
    #sidebar,
    #sidebar-tabs,
    .sidebar-inner-container {
        display: flex;
        flex-direction: column;
    }

    #sidebar {
        background: var(--sidebar-bg);
        height: 100vh;
        width: calc(var(--sidebar-width) + var(--sidebar-inner-padding) * 2);
        position: sticky;
    }

    #sidebar-tabs {
        height: 100%;
        justify-content: space-between;
        padding: var(--sidebar-inner-padding);
        padding-bottom: var(--sidebar-tab-padding);
        overflow-y: scroll;
    }

    @media screen and (max-width: 535px) {
        #sidebar,
        #sidebar-tabs,
        .sidebar-inner-container {
            flex-direction: row;
        }

        #sidebar {
            width: 100%;
            height: var(--sidebar-height-mobile);
            position: fixed;
            bottom: 0;
            justify-content: center;
            align-items: flex-start;
            z-index: 3;
            padding: var(--sidebar-inner-padding) 0;
        }

        #sidebar::before {
            content: "";
            z-index: 1;
            width: 100%;
            height: 100%;
            display: block;
            position: absolute;
            pointer-events: none;
            background: var(--sidebar-mobile-gradient);
        }

        #sidebar-tabs {
            overflow-y: visible;
            overflow-x: scroll;
            padding: 0;
            height: fit-content;
        }

        #sidebar :global(.sidebar-inner-container:first-child) {
            padding-left: calc(var(--border-radius) * 1.5);
        }

        #sidebar :global(.sidebar-inner-container:last-child) {
            padding-right: calc(var(--border-radius) * 1.5);
        }
    }
</style>
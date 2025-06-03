<script>
    import AgendaSearchBox from "$components/agenda/AgendaSearchBox.svelte";
    import EngageMintLogo from "$components/misc/EngageMintLogo.svelte";
    import RecentAgendas from "$components/agenda/RecentAgendas.svelte";
</script>

<svelte:head>
    <title>EngageMint - Stay Informed</title>
</svelte:head>

<div id="engagemint-home-container" class="center-column-container">
    <RecentAgendas />
    <main
        id="engagemint-home"
        tabindex="-1"
        data-first-focus
    >
        <EngageMintLogo />
        <AgendaSearchBox />
    </main>
    <div id="civic-note">
        Empowering civic engagement through accessible local government information
    </div>
</div>

<style>
    #engagemint-home-container {
        padding: var(--padding);
        overflow: hidden;
    }

    #engagemint-home {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        width: 100%;
        height: 100%;
        gap: 15px;
    }

    #civic-note {
        bottom: 0;
        color: var(--gray);
        font-size: 12px;
        text-align: center;
        padding-bottom: 6px;
        font-weight: 500;
    }

    @media screen and (max-width: 535px) {
        #engagemint-home-container {
            padding-top: calc(var(--padding) / 2);
        }

        #civic-note {
            font-size: 11px;
            padding-bottom: 0;
        }
    }
</style>
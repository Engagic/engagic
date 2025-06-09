<script>
    import { onMount } from "svelte";
    import { slide } from "svelte/transition";
    import ZipcodeSearch from "$components/search/ZipcodeSearch.svelte";
    import EngagicLogo from "$components/misc/engagicLogo.svelte";
    import RecentAgendas from "$components/agenda/RecentAgendas.svelte";
    import AgendaSearchBox from "$components/agenda/AgendaSearchBox.svelte";
    
    let showAdvanced = $state(false);
    let mounted = $state(false);
    
    onMount(() => {
        mounted = true;
    });
</script>

<svelte:head>
    <title>engagic - Democracy Made Accessible</title>
    <meta name="description" content="Find local government meetings and decisions that affect your community. Subscribe to topics you care about and never miss important civic discussions." />
</svelte:head>

<div id="engagic-home-container" class:mounted>
    <div class="hero-section">
        <EngagicLogo />
        <div class="hero-text">
            <h1>Your Voice in Local Government</h1>
            <p>Stay informed about the decisions that shape your community. Find meetings, track issues you care about, and make your voice heard.</p>
        </div>
    </div>

    <main id="engagic-home" tabindex="-1" data-first-focus>
        <ZipcodeSearch />
        
        <div class="advanced-options">
            <button 
                class="toggle-advanced"
                onclick={() => showAdvanced = !showAdvanced}
            >
                {showAdvanced ? 'Hide' : 'Show'} Advanced Search
            </button>
            
            {#if showAdvanced}
                <div class="advanced-panel" transition:slide>
                    <AgendaSearchBox />
                </div>
            {/if}
        </div>
    </main>

    <RecentAgendas />
    
    <div id="impact-note">
        <div class="impact-stats">
            <div class="stat">
                <span class="stat-number">10,000+</span>
                <span class="stat-label">Meeting Documents Processed</span>
            </div>
            <div class="stat">
                <span class="stat-number">50+</span>
                <span class="stat-label">Cities Covered</span>
            </div>
            <div class="stat">
                <span class="stat-number">Free</span>
                <span class="stat-label">No Tracking, No Ads</span>
            </div>
        </div>
        <p>Making democracy accessible, one community at a time.</p>
    </div>
</div>

<style>
    #engagic-home-container {
        padding: 0;
        overflow-y: auto;
        height: 100vh;
        background: linear-gradient(135deg, 
            rgba(29, 78, 216, 0.03) 0%, 
            rgba(59, 130, 246, 0.02) 50%, 
            rgba(16, 185, 129, 0.03) 100%);
        opacity: 0;
        transform: translateY(20px);
        transition: all 0.6s ease;
    }

    #engagic-home-container.mounted {
        opacity: 1;
        transform: translateY(0);
    }

    .hero-section {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        padding: 40px 20px 20px;
        max-width: 800px;
        margin: 0 auto;
    }

    .hero-text {
        margin-top: 24px;
        max-width: 600px;
    }

    .hero-text h1 {
        font-size: 2.5rem;
        font-weight: 700;
        margin: 0 0 16px 0;
        color: var(--secondary);
        line-height: 1.2;
        letter-spacing: -0.02em;
    }

    .hero-text p {
        font-size: 1.25rem;
        color: var(--gray);
        margin: 0;
        line-height: 1.6;
        font-weight: 400;
    }

    #engagic-home {
        display: flex;
        flex-direction: column;
        align-items: center;
        width: 100%;
        max-width: 800px;
        margin: 0 auto;
        padding: 0 20px 40px;
        gap: 32px;
    }

    .advanced-options {
        width: 100%;
        max-width: 680px;
    }

    .toggle-advanced {
        display: block;
        margin: 0 auto 16px;
        padding: 8px 16px;
        background: transparent;
        border: 1px solid var(--input-border);
        border-radius: 8px;
        color: var(--gray);
        font-size: 0.875rem;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .toggle-advanced:hover {
        border-color: var(--civic-blue);
        color: var(--civic-blue);
    }

    .advanced-panel {
        padding: 20px;
        background: var(--white);
        border: 1px solid var(--input-border);
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    }

    #impact-note {
        background: var(--white);
        border-top: 1px solid var(--input-border);
        padding: 40px 20px;
        text-align: center;
        margin-top: 40px;
    }

    .impact-stats {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 32px;
        max-width: 800px;
        margin: 0 auto 24px;
    }

    .stat {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 8px;
    }

    .stat-number {
        font-size: 2rem;
        font-weight: 700;
        background: var(--civic-gradient);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    .stat-label {
        font-size: 0.9rem;
        color: var(--gray);
        font-weight: 500;
        text-align: center;
    }

    #impact-note p {
        color: var(--gray);
        font-size: 1rem;
        margin: 0;
        font-weight: 500;
    }

    @media screen and (max-width: 768px) {
        .hero-text h1 {
            font-size: 2rem;
        }

        .hero-text p {
            font-size: 1.125rem;
        }

        .impact-stats {
            grid-template-columns: 1fr;
            gap: 24px;
        }

        .stat-number {
            font-size: 1.75rem;
        }
    }

    @media screen and (max-width: 640px) {
        .hero-section {
            padding: 20px 16px 16px;
        }

        #engagic-home {
            padding: 0 16px 32px;
            gap: 24px;
        }

        .hero-text h1 {
            font-size: 1.75rem;
        }

        .hero-text p {
            font-size: 1rem;
        }

        #impact-note {
            padding: 32px 16px;
        }
    }
</style>
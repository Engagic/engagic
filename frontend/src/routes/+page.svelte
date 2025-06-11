<script>
    import ZipcodeSearch from "$components/search/ZipcodeSearch.svelte";
    import EngagicLogo from "$components/misc/engagicLogo.svelte";
</script>

<svelte:head>
    <title>engagic - Democracy Made Accessible</title>
    <meta name="description" content="Find local government meetings and decisions that affect your community" />
</svelte:head>

<div class="container">
    <div class="hero">
        <EngagicLogo />
        <h1>Find Local Government Meetings</h1>
        <p>Enter your zipcode or city name to see upcoming meetings and agendas</p>
    </div>

    <div class="search-section">
        <ZipcodeSearch />
    </div>
</div>

<style>
    .container {
        min-height: 100vh;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 2rem;
        background: linear-gradient(135deg, 
            rgba(29, 78, 216, 0.03) 0%, 
            rgba(59, 130, 246, 0.02) 50%, 
            rgba(16, 185, 129, 0.03) 100%);
    }

    .hero {
        text-align: center;
        margin-bottom: 3rem;
        max-width: 600px;
    }

    .hero h1 {
        font-size: 2.5rem;
        font-weight: 600;
        margin: 1.5rem 0 1rem 0;
        color: var(--secondary);
        line-height: 1.2;
    }

    .hero p {
        font-size: 1.125rem;
        color: var(--gray);
        margin: 0;
        line-height: 1.6;
    }

    .search-section {
        width: 100%;
        max-width: 500px;
    }

    @media screen and (max-width: 768px) {
        .container {
            padding: 1rem;
        }
        
        .hero h1 {
            font-size: 2rem;
        }

        .hero p {
            font-size: 1rem;
        }
    }
</style>
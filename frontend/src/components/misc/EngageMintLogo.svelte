<script lang="ts">
    let loaded = $state(false);
</script>

<div
    class="engagemint-logo"
    class:loaded
>
    <div class="logo-icon">
        🏛️
    </div>
    <div class="logo-text">
        <h1>EngageMint</h1>
        <p class="tagline">Civic engagement made simple</p>
    </div>
</div>

<style>
    .engagemint-logo {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 12px;
        margin-bottom: 8px;
        opacity: 0;
        transform: translateY(10px);
        transition: opacity 0.3s ease, transform 0.3s ease;
    }

    .engagemint-logo.loaded {
        opacity: 1;
        transform: translateY(0);
    }

    .logo-icon {
        font-size: 64px;
        line-height: 1;
        margin-bottom: -8px;
    }

    .logo-text {
        text-align: center;
    }

    .logo-text h1 {
        font-size: 28px;
        font-weight: 600;
        margin: 0;
        letter-spacing: -1.5px;
        color: var(--secondary);
    }

    .tagline {
        font-size: 14px;
        color: var(--gray);
        margin: 4px 0 0 0;
        font-weight: 500;
    }

    @media screen and (max-width: 535px) {
        .logo-icon {
            font-size: 48px;
        }

        .logo-text h1 {
            font-size: 24px;
        }

        .tagline {
            font-size: 13px;
        }
    }

    /* Auto-load effect */
    :global(body) .engagemint-logo {
        animation: logoLoad 0.6s ease forwards;
    }

    @keyframes logoLoad {
        0% {
            opacity: 0;
            transform: translateY(10px);
        }
        100% {
            opacity: 1;
            transform: translateY(0);
        }
    }
</style>
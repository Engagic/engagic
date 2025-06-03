<script lang="ts">
    import { page } from "$app/stores";
</script>

<a href="/" class="engagemint-icon" aria-label="EngageMint home">
    <div class="icon-wrapper">
        🏛️
    </div>
    <div class="icon-text">EM</div>
</a>

<style>
    .engagemint-icon {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-decoration: none;
        color: var(--sidebar-highlight);
        padding: var(--sidebar-tab-padding);
        margin: var(--sidebar-inner-padding);
        margin-bottom: calc(var(--sidebar-inner-padding) * 2);
        border-radius: var(--border-radius);
        transition: background-color 0.15s;
        gap: 2px;
    }

    .engagemint-icon:hover {
        background-color: var(--button-hover-transparent);
    }

    .icon-wrapper {
        font-size: 24px;
        line-height: 1;
    }

    .icon-text {
        font-size: var(--sidebar-font-size);
        font-weight: 600;
        letter-spacing: 0.5px;
    }

    @media screen and (max-width: 535px) {
        .engagemint-icon {
            display: none;
        }
    }
</style>
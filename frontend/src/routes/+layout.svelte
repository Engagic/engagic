<script lang="ts">
    import "../app.css";
</script>

<svelte:head>
    <title>engagic - Democracy Made Accessible</title>
    <meta name="description" content="Find local government meetings and decisions that affect your community" />
</svelte:head>

<main>
    <slot></slot>
</main>

<style>
    main {
        min-height: 100vh;
        background: var(--primary);
        color: var(--secondary);
    }
</style>
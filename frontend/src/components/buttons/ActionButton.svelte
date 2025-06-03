<script lang="ts">
    export let id: string;
    export let click = () => {};
    export let disabled: boolean = false;
</script>

<button 
    id="button-{id}" 
    class="button" 
    {disabled}
    on:click={click}
>
    <slot></slot>
</button>
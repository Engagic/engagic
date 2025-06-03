<script lang="ts">
    export let size: number = 24;
    export let stroke: string = "currentColor";
</script>

<svg 
    width={size} 
    height={size} 
    viewBox="0 0 24 24" 
    fill="none" 
    {stroke} 
    stroke-width="2" 
    stroke-linecap="round" 
    stroke-linejoin="round"
>
    <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>
</svg>
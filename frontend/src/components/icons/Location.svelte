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
    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
    <circle cx="12" cy="10" r="3"/>
</svg>
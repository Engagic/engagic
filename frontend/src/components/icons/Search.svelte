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
    <circle cx="11" cy="11" r="8"/>
    <path d="m21 21-4.35-4.35"/>
</svg>
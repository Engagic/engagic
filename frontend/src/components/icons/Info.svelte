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
    <circle cx="12" cy="12" r="10"/>
    <path d="M12 16v-4"/>
    <path d="M12 8h.01"/>
</svg>
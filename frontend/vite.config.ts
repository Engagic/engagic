import { sveltekit } from '@sveltejs/kit/vite';
import { enhancedImages } from '@sveltejs/enhanced-img';
import { defineConfig } from 'vite';
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig({
    plugins: [
        enhancedImages(),
        sveltekit(),
        // Bundle analyzer - generates stats.html after build
        visualizer({
            filename: 'stats.html',
            gzipSize: true,
            brotliSize: true
        })
    ],
    resolve: {
        alias: {
            $components: '/src/components',
            $lib: '/src/lib'
        }
    }
    // Note: manualChunks removed - incompatible with SvelteKit Cloudflare adapter
    // (deps marked as external for SSR)
});
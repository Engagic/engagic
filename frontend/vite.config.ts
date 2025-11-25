import { sveltekit } from '@sveltejs/kit/vite';
import { enhancedImages } from '@sveltejs/enhanced-img';
import { defineConfig } from 'vite';

export default defineConfig({
    plugins: [
        enhancedImages(),
        sveltekit()
    ],
    resolve: {
        alias: {
            $components: '/src/components',
            $lib: '/src/lib'
        }
    }
});
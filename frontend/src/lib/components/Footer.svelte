<footer class="footer">
	<p class="tagline">
		by continuing you adhere to our <a href="/about/terms" class="inline-link">terms</a>. made with love and rizz
	</p>
	<a href="/about" class="footer-link">About</a>
</footer>

<style>
	.footer {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-md);
		padding: var(--space-2xl) 0;
		margin-top: var(--space-3xl);
		border-top: 1px solid var(--border-primary);
	}

	.tagline {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.875rem;
		color: var(--text-secondary);
		text-align: center;
		margin: 0;
		line-height: 1.6;
	}

	.inline-link {
		color: var(--civic-blue);
		text-decoration: underline;
		transition: color var(--transition-fast);
	}

	.inline-link:hover {
		color: var(--civic-accent);
	}

	.footer-link {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.875rem;
		color: var(--civic-blue);
		text-decoration: none;
		transition: color var(--transition-fast);
	}

	.footer-link:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}
</style>
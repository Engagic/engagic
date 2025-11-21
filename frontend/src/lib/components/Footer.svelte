<footer class="site-footer">
	<p class="footer-message">
		by continuing you adhere to our <a href="/about/terms" class="terms-link">terms</a>. made with love and rizz
	</p>
	<a href="/about" class="about-nav-link">About</a>
</footer>

<style>
	.site-footer {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-md);
		padding: var(--space-2xl) 0;
		margin-top: var(--space-3xl);
		border-top: 1px solid var(--border-primary);
	}

	.footer-message {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.875rem;
		color: var(--text-secondary);
		text-align: center;
		margin: 0;
		line-height: 1.6;
	}

	.terms-link {
		color: var(--civic-blue);
		text-decoration: underline;
		transition: color var(--transition-fast);
	}

	.terms-link:hover {
		color: var(--civic-accent);
	}

	.about-nav-link {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.875rem;
		color: var(--civic-blue);
		text-decoration: none;
		transition: color var(--transition-fast);
	}

	.about-nav-link:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}
</style>

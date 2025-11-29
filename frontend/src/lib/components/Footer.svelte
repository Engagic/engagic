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
		padding: var(--space-xl) 0;
		margin-top: var(--space-3xl);
		border-top: 1px solid var(--border);
	}

	.footer-message {
		font-size: var(--text-sm);
		color: var(--text-muted);
		text-align: center;
		margin: 0;
	}

	.terms-link {
		color: var(--color-action);
		text-decoration: underline;
		transition: color var(--transition-fast);
	}

	.terms-link:hover {
		color: var(--color-action-hover);
	}

	.about-nav-link {
		font-size: var(--text-sm);
		color: var(--color-action);
		text-decoration: none;
		transition: color var(--transition-fast);
	}

	.about-nav-link:hover {
		color: var(--color-action-hover);
		text-decoration: underline;
	}
</style>

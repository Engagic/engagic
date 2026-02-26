<script lang="ts">
	import SeoHead from '$lib/components/SeoHead.svelte';

	const contacts = {
		github: 'https://github.com/Engagic/engagic',
		email: 'mailto:hello@engagic.org',
		issues: 'https://github.com/Engagic/engagic/issues',
		twitter: 'https://twitter.com/engagicc'
	};
</script>

<SeoHead
	title="Community & Ecosystem - engagic"
	description="Get help, contribute code, or connect with the Engagic community"
	url="https://engagic.org/about/community"
/>

<article class="community-content">
	<section class="section">
		<h1 class="section-heading">Connect With Us</h1>
		<div class="contact-grid">
			<a href={contacts.github} target="_blank" rel="noopener" class="contact-card">
				<div class="contact-icon github-icon">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>
					</svg>
				</div>
				<h3 class="contact-title">GitHub</h3>
				<p>View source code, fork the project, or contribute to development. All code is AGPL-3.0 licensed and open for collaboration.</p>
			</a>

			<a href={contacts.email} class="contact-card">
				<div class="contact-icon email-icon">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<rect x="3" y="5" width="18" height="14" rx="2"/>
						<path d="M3 7l9 6 9-6"/>
					</svg>
				</div>
				<h3 class="contact-title">Email</h3>
				<p>General inquiries, partnership requests, or media questions. We're humans and we respond. hello@engagic.org</p>
			</a>

			<a href={contacts.issues} target="_blank" rel="noopener" class="contact-card">
				<div class="contact-icon issues-icon">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<circle cx="12" cy="12" r="10"/>
						<line x1="12" y1="8" x2="12" y2="12"/>
						<line x1="12" y1="16" x2="12.01" y2="16"/>
					</svg>
				</div>
				<h3 class="contact-title">Report Issues</h3>
				<p>Found a bug or have a feature request? Open an issue on GitHub. We track all development publicly.</p>
			</a>

			<a href={contacts.twitter} target="_blank" rel="noopener" class="contact-card">
				<div class="contact-icon twitter-icon">
					<svg viewBox="0 0 24 24" fill="currentColor">
						<path d="M23.643 4.937c-.835.37-1.732.62-2.675.733.962-.576 1.7-1.49 2.048-2.578-.9.534-1.897.922-2.958 1.13-.85-.904-2.06-1.47-3.4-1.47-2.572 0-4.658 2.086-4.658 4.66 0 .364.042.718.12 1.06-3.873-.195-7.304-2.05-9.602-4.868-.4.69-.63 1.49-.63 2.342 0 1.616.823 3.043 2.072 3.878-.764-.025-1.482-.234-2.11-.583v.06c0 2.257 1.605 4.14 3.737 4.568-.392.106-.803.162-1.227.162-.3 0-.593-.028-.877-.082.593 1.85 2.313 3.198 4.352 3.234-1.595 1.25-3.604 1.995-5.786 1.995-.376 0-.747-.022-1.112-.065 2.062 1.323 4.51 2.093 7.14 2.093 8.57 0 13.255-7.098 13.255-13.254 0-.2-.005-.402-.014-.602.91-.658 1.7-1.477 2.323-2.41z"/>
					</svg>
				</div>
				<h3 class="contact-title">Twitter</h3>
				<p>Follow @engagicc for updates, civic tech commentary, and the occasional hot take on local government transparency.</p>
			</a>
		</div>
	</section>

	<section class="section">
		<h2 class="section-heading">Support Guidelines</h2>

		<div class="guideline">
			<h3 class="guideline-heading">Bug Reports</h3>
			<p>If you encounter a bug, please open a GitHub issue with:</p>
			<ul>
				<li>Clear description of the problem</li>
				<li>Steps to reproduce</li>
				<li>Expected vs actual behavior</li>
				<li>Browser/system information if relevant</li>
			</ul>
		</div>

		<div class="guideline">
			<h3 class="guideline-heading">Feature Requests</h3>
			<p>Have an idea? Open a GitHub issue tagged "enhancement" and describe:</p>
			<ul>
				<li>The problem you're trying to solve</li>
				<li>How the feature would help</li>
				<li>Any alternatives you've considered</li>
			</ul>
		</div>

		<div class="guideline">
			<h3 class="guideline-heading">General Questions</h3>
			<p>For questions about using Engagic, data accuracy, or partnership opportunities, email us at hello@engagic.org. We aim to respond within 48 hours.</p>
		</div>

		<p class="note"><strong>Best Effort Support:</strong> Engagic is maintained by a small team. We provide support on a best-effort basis and prioritize issues that affect the most users.</p>
	</section>
</article>

<style>
	.community-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-xl);
		padding-bottom: var(--space-xl);
		color: var(--text-primary);
	}

	.section {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.section-heading {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
		line-height: 1.2;
	}

	h1.section-heading {
		font-size: 2.5rem;
	}

	.contact-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: var(--space-lg);
	}

	.contact-card {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
		padding: var(--space-xl);
		background: var(--surface-primary);
		border: 2px solid var(--border-primary);
		border-radius: var(--radius-md);
		text-decoration: none;
		transition: all var(--transition-normal);
		cursor: pointer;
	}

	.contact-card:hover {
		border-color: var(--civic-blue);
		box-shadow: 0 8px 24px var(--shadow-lg);
		transform: translateY(-2px);
	}

	.contact-icon {
		width: 56px;
		height: 56px;
		border-radius: var(--radius-md);
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.contact-icon svg {
		width: 28px;
		height: 28px;
		stroke: white;
	}

	.github-icon {
		background: #8842cd;
	}

	.email-icon {
		background: #4f46e5;
	}

	.issues-icon {
		background: #f97316;
	}

	.twitter-icon {
		background: #1da1f2;
	}

	.twitter-icon svg {
		fill: white;
		stroke: none;
	}

	.contact-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.contact-card p {
		font-size: 1.1rem;
		line-height: 1.7;
		color: var(--text-primary);
		margin: 0;
	}

	.guideline {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
		padding: var(--space-lg);
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-md);
	}

	.guideline-heading {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin: 0;
	}

	.guideline p {
		font-size: 1.1rem;
		line-height: 1.7;
		color: var(--text-primary);
		margin: 0;
	}

	.guideline ul {
		font-size: 1.1rem;
		line-height: 1.7;
		color: var(--text-primary);
		margin: 0;
		padding-left: var(--space-lg);
	}

	.guideline li {
		margin-bottom: var(--space-xs);
	}

	.note {
		font-size: 1.1rem;
		line-height: 1.7;
		color: var(--text-primary);
		background: var(--surface-secondary);
		border-left: 3px solid var(--civic-blue);
		padding: var(--space-md);
		border-radius: var(--radius-sm);
		font-style: italic;
		margin: 0;
	}

	.note strong {
		color: var(--text-primary);
	}

	@media (max-width: 768px) {
		h1.section-heading {
			font-size: 2rem;
		}

		.section-heading {
			font-size: 1.5rem;
		}

		.contact-grid {
			grid-template-columns: 1fr;
		}

		.contact-card {
			padding: var(--space-lg);
		}

		.guideline {
			padding: var(--space-md);
		}
	}
</style>

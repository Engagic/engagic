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
		<h1 class="page-title">Connect With Us</h1>
	</section>

	<section class="section">
		<div class="section-rule">Channels</div>
		<div class="contact-list">
			<a href={contacts.github} target="_blank" rel="noopener" class="contact-row">
				<span class="contact-name">GitHub</span>
				<span class="contact-desc">View source code, fork the project, or contribute to development. All code is AGPL-3.0 licensed.</span>
			</a>

			<a href={contacts.email} class="contact-row">
				<span class="contact-name">Email</span>
				<span class="contact-desc">General inquiries, partnership requests, or media questions. hello@engagic.org</span>
			</a>

			<a href={contacts.issues} target="_blank" rel="noopener" class="contact-row">
				<span class="contact-name">Issues</span>
				<span class="contact-desc">Found a bug or have a feature request? Open an issue on GitHub. We track all development publicly.</span>
			</a>

			<a href={contacts.twitter} target="_blank" rel="noopener" class="contact-row">
				<span class="contact-name">Twitter</span>
				<span class="contact-desc">Follow @engagicc for updates, civic tech commentary, and the occasional hot take on local government transparency.</span>
			</a>
		</div>
	</section>

	<section class="section">
		<div class="section-rule">Support Guidelines</div>

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
		gap: var(--space-2xl);
		padding-bottom: var(--space-xl);
		color: var(--text-primary);
	}

	.section {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.page-title {
		font-family: var(--font-display);
		font-size: clamp(2rem, 5vw, 3rem);
		font-weight: 400;
		color: var(--text-primary);
		margin: 0;
		line-height: 1.1;
		letter-spacing: -0.02em;
	}

	.section-rule {
		font-family: var(--font-body);
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--civic-gray);
		padding-bottom: 0.5rem;
		border-bottom: 2px solid var(--text-primary);
		margin: 0;
	}

	.contact-list {
		display: flex;
		flex-direction: column;
	}

	.contact-row {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 1.25rem 0;
		border-bottom: 1px solid var(--border-primary);
		text-decoration: none;
		color: inherit;
		transition: padding-left 0.2s ease;
	}

	.contact-row:hover {
		padding-left: 8px;
	}

	.contact-name {
		font-family: var(--font-display);
		font-size: 1.15rem;
		font-weight: 400;
		color: var(--text-primary);
	}

	.contact-desc {
		font-size: 0.95rem;
		line-height: 1.6;
		color: var(--text-secondary);
	}

	.guideline {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
		padding: var(--space-md) 0;
		border-bottom: 1px solid var(--border-primary);
	}

	.guideline:last-of-type {
		border-bottom: none;
	}

	.guideline-heading {
		font-family: var(--font-display);
		font-size: 1.1rem;
		font-weight: 400;
		color: var(--text-primary);
		margin: 0;
	}

	.guideline p {
		font-size: 1rem;
		line-height: 1.7;
		color: var(--text-secondary);
		margin: 0;
	}

	.guideline ul {
		font-size: 1rem;
		line-height: 1.7;
		color: var(--text-secondary);
		margin: 0;
		padding-left: var(--space-lg);
	}

	.guideline li {
		margin-bottom: var(--space-xs);
	}

	.note {
		font-size: 0.95rem;
		line-height: 1.7;
		color: var(--text-secondary);
		border-left: 2px solid var(--civic-blue);
		padding-left: var(--space-md);
		font-style: italic;
		margin: 0;
	}

	.note strong {
		color: var(--text-primary);
	}

	@media (max-width: 768px) {
		.page-title {
			font-size: 2rem;
		}

		.contact-desc {
			font-size: 0.9rem;
		}
	}
</style>

<svelte:head>
	<title>About Engagic - What We Do</title>
	<meta name="description" content="Learn about Engagic's mission to make local government meetings accessible through AI-powered summaries" />
</svelte:head>

<article class="about-content">
	<section class="section">
		<h1 class="section-heading">Our Mission</h1>
		<p>Engagic is an open-source civic technology platform that automatically finds and summarizes local government meetings across the United States.</p>
		<p>Democracy works better when everyone can participate. Government meetings are often hard to find, harder to understand, and buried in bureaucratic language. We changed that.</p>
	</section>

	<section class="section">
		<h2 class="section-heading">What We Do</h2>
		<div class="feature-list">
			<div class="feature-item">
				<h3 class="feature-heading">Monitor</h3>
				<p>Our system can continuously check city websites for new meeting agendas and packets across 600+ cities.</p>
			</div>
			<div class="feature-item">
				<h3 class="feature-heading">Process</h3>
				<p>Advanced AI reads through dense government documents and extracts what matters - budget decisions, zoning changes, public hearings.</p>
			</div>
			<div class="feature-item">
				<h3 class="feature-heading">Deliver Clarity</h3>
				<p>Clean, readable summaries that highlight key decisions, citizen impact, and public participation opportunities.</p>
			</div>
		</div>
		<p>No more digging through 100+ page PDFs. Search your zip code and get the important stuff in plain English.</p>
	</section>

	<section class="section">
		<h2 class="section-heading">Our Principles</h2>
		<div class="principles-grid">
			<div class="principle">
				<h3 class="principle-heading">Open Source</h3>
				<p>All our code is publicly available and auditable (AGPL-3.0). Democracy should be transparent, and so should the tools that support it.</p>
			</div>

			<div class="principle">
				<h3 class="principle-heading">No Agenda</h3>
				<p>We don't editorialize or take political positions. We just make information accessible. Our AI summarizes meetings factually.</p>
			</div>

			<div class="principle">
				<h3 class="principle-heading">Privacy First</h3>
				<p>We don't track users or collect personal data. Civic engagement shouldn't require surveillance. Search freely, participate freely.</p>
			</div>

			<div class="principle">
				<h3 class="principle-heading">Public Data Stays Public</h3>
				<p>Government meeting information belongs to everyone. We built this infrastructure to make that access real, not theoretical.</p>
			</div>
		</div>
	</section>

	<section class="section highlight-section">
		<h2 class="section-heading">The Philosophy</h2>
		<p class="philosophy-lead">Civic data should be open. Infrastructure costs money. We're balancing both.</p>

		<div class="use-case-list">
			<p>Individual checking your city's meetings → <strong>use it freely</strong></p>
			<p>Nonprofit fighting for housing justice → <strong>let's partner</strong></p>
			<p>Journalist covering local government → <strong>we're here to help</strong></p>
			<p>Researcher studying civic engagement → <strong>the data is yours</strong></p>
		</div>

		<p class="contact-footer">
			<strong>Questions?</strong> <a href="mailto:hello@engagic.org">hello@engagic.org</a> - We're humans. Let's talk.
		</p>
	</section>
</article>

<style>
	.about-content {
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

	.about-content p {
		font-size: 1.125rem;
		line-height: 1.75;
		color: var(--text-secondary);
		margin: 0;
	}

	.feature-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-lg);
		padding-left: var(--space-md);
		border-left: 2px solid var(--border-primary);
	}

	.feature-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.feature-heading {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin: 0;
	}

	.feature-item p {
		font-size: 1.0625rem;
		line-height: 1.7;
	}

	.principles-grid {
		display: grid;
		gap: var(--space-lg);
	}

	.principle {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
		padding: var(--space-lg);
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-md);
		transition: all var(--transition-normal);
	}

	.principle:hover {
		border-color: var(--civic-blue);
		box-shadow: 0 4px 16px var(--shadow-md);
	}

	.principle-heading {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin: 0;
	}

	.principle p {
		font-size: 1.0625rem;
		line-height: 1.7;
	}

	.highlight-section {
		background: var(--surface-secondary);
		border: 2px solid var(--civic-blue);
		border-radius: var(--radius-lg);
		padding: var(--space-2xl);
		gap: var(--space-xl);
	}

	.philosophy-lead {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		font-weight: 500;
		color: var(--text-primary);
		line-height: 1.6;
	}

	.use-case-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.use-case-list p {
		font-size: 1.0625rem;
		line-height: 1.7;
		padding: var(--space-md);
		background: var(--surface-primary);
		border-radius: var(--radius-sm);
		border-left: 3px solid var(--civic-blue);
	}

	.use-case-list strong {
		color: var(--text-primary);
		font-weight: 600;
	}

	.contact-footer {
		font-size: 1.0625rem;
		line-height: 1.7;
		padding-top: var(--space-lg);
		border-top: 1px solid var(--border-primary);
	}

	.contact-footer a {
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 600;
		transition: color var(--transition-fast);
	}

	.contact-footer a:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}

	@media (max-width: 768px) {
		h1.section-heading {
			font-size: 2rem;
		}

		.section-heading {
			font-size: 1.5rem;
		}

		.about-content p {
			font-size: 1rem;
		}

		.highlight-section {
			padding: var(--space-lg);
		}

		.principles-grid {
			grid-template-columns: 1fr;
		}
	}
</style>

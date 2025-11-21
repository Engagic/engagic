<script lang="ts">
	import Footer from '$lib/components/Footer.svelte';

	// Smooth scroll to section (cobalt pattern)
	function scrollToSection(id: string) {
		const element = document.getElementById(id);
		if (element) {
			element.scrollIntoView({ behavior: 'smooth', block: 'start' });
		}
	}

	// Snapshot: Preserve scroll position during navigation
	export const snapshot = {
		capture: () => ({
			scrollY: typeof window !== 'undefined' ? window.scrollY : 0
		}),
		restore: (values: { scrollY: number }) => {
			if (typeof window !== 'undefined' && typeof values.scrollY === 'number') {
				setTimeout(() => window.scrollTo(0, values.scrollY), 0);
			}
		}
	};
</script>

<svelte:head>
	<title>Terms of Service - Engagic</title>
	<meta name="description" content="Engagic API Terms of Service - Usage tiers, attribution requirements, and acceptable use policy" />
</svelte:head>

<article class="terms-content">

	<h1 class="page-heading">Terms of Service</h1>
	<p class="last-updated">Last Updated: November 17, 2025</p>

	<!-- Content Sections -->
	<main class="terms-content">
		<section id="about" class="terms-section">
			<h2>About Engagic</h2>
			<p>Engagic is an open-source civic technology platform (AGPL-3.0 licensed) that provides access to public meeting data from local governments across the United States. The code is free and open. The hosted API service (api.engagic.org) is provided as a public good with reasonable usage limits.</p>
		</section>

		<section id="deal" class="terms-section">
			<h2>The Deal</h2>
			<p><strong>Public data stays public.</strong> We believe government meeting information should be accessible to everyone. We built this infrastructure to make that happen.</p>
			<p><strong>The code is free.</strong> Engagic is AGPL-3.0 licensed. If you want unlimited access and can handle your own infrastructure costs (servers, LLM processing, bandwidth), clone the repo and self-host. No restrictions.</p>
			<p><strong>The hosted API has limits.</strong> Running this service costs real money (LLM processing, server hosting, labor). We provide a free tier for reasonable personal use. Heavy usage requires partnership or payment.</p>
		</section>

		<section id="tiers" class="terms-section">
			<h2>Usage Tiers</h2>

			<div class="tier-grid">
				<div class="tier-card tier-free">
					<h3 class="tier-name">Resident Tier</h3>
					<div class="tier-limits">
						<div class="limit-item">
							<span class="limit-value">30</span>
							<span class="limit-unit">req/min</span>
						</div>
						<div class="limit-divider">•</div>
						<div class="limit-item">
							<span class="limit-value">300</span>
							<span class="limit-unit">req/day</span>
						</div>
					</div>
					<p class="tier-use-case">Personal research, casual browsing, individual civic engagement</p>
					<p class="tier-cost">Free forever</p>
					<p class="tier-requirement">No registration required</p>
				</div>

				<div class="tier-card tier-hacktivist">
					<h3 class="tier-name">Hacktivist Tier</h3>
					<div class="tier-limits">
						<div class="limit-item">
							<span class="limit-value">100</span>
							<span class="limit-unit">req/min</span>
						</div>
						<div class="limit-divider">•</div>
						<div class="limit-item">
							<span class="limit-value">5,000</span>
							<span class="limit-unit">req/day</span>
						</div>
					</div>
					<p class="tier-use-case">501(c)(3) nonprofits, accredited journalists, civic advocacy organizations</p>
					<div class="tier-requirements">
						<p class="tier-requirement-title">Requirements:</p>
						<ul>
							<li>Proof of nonprofit status or press credentials</li>
							<li>Public attribution of data source</li>
							<li>Email contact for partnership</li>
						</ul>
					</div>
					<p class="tier-cost">Free with attribution</p>
					<a href="mailto:hello@engagic.org" class="tier-contact">Contact: hello@engagic.org</a>
				</div>

				<div class="tier-card tier-enterprise">
					<h3 class="tier-name">Enterprise Tier</h3>
					<div class="tier-limits">
						<div class="limit-item">
							<span class="limit-value">1k+</span>
							<span class="limit-unit">req/min</span>
						</div>
						<div class="limit-divider">•</div>
						<div class="limit-item">
							<span class="limit-value">100k+</span>
							<span class="limit-unit">req/day</span>
						</div>
					</div>
					<p class="tier-use-case">Commercial products, for-profit ventures, paid research services</p>
					<div class="tier-requirements">
						<p class="tier-requirement-title">Requirements:</p>
						<ul>
							<li>Commercial license agreement</li>
							<li>Payment for infrastructure costs</li>
						</ul>
					</div>
					<p class="tier-cost">Contact for pricing</p>
					<a href="mailto:admin@motioncount.com" class="tier-contact">Contact: admin@motioncount.com</a>
				</div>
			</div>
		</section>

		<section id="attribution" class="terms-section">
			<h2>Attribution Requirements</h2>
			<p>If you use Engagic data in a public-facing product or publication (website, app, research paper, article), you must provide <strong>clear attribution</strong>:</p>

			<div class="code-block">
				<p class="code-label">Minimum acceptable attribution:</p>
				<code>Data provided by Engagic (engagic.org)</code>
			</div>

			<div class="code-block">
				<p class="code-label">Preferred attribution (with link):</p>
				<code>Meeting data processed and provided by <a href="https://engagic.org">Engagic</a>,<br>an open-source civic technology platform.</code>
			</div>

			<div class="attribution-rules">
				<div class="rule-group">
					<h3>Attribution Waived For:</h3>
					<ul>
						<li>Personal/private use (not public-facing)</li>
						<li>Basic tier users (though appreciated)</li>
					</ul>
				</div>

				<div class="rule-group">
					<h3>Attribution Required For:</h3>
					<ul>
						<li>Nonprofit/journalist tier</li>
						<li>Any commercial use</li>
						<li>Any derivative products/services</li>
					</ul>
				</div>
			</div>
		</section>

		<section id="acceptable-use" class="terms-section">
			<h2>Acceptable Use</h2>

			<div class="use-policies">
				<div class="policy-allowed">
					<h3>You MAY:</h3>
					<ul>
						<li>Use the API for personal research and civic engagement</li>
						<li>Build tools that help citizens understand local government</li>
						<li>Cite Engagic data in journalism, research, or advocacy</li>
						<li>Self-host the open-source code without restriction (AGPL-3.0)</li>
						<li>Use the data for nonprofit civic tech projects with attribution</li>
					</ul>
				</div>

				<div class="policy-prohibited">
					<h3>You MAY NOT:</h3>
					<ul>
						<li>Resell raw Engagic data without adding significant value</li>
						<li>Use automated tools to circumvent rate limits</li>
						<li>Use the API in ways that harm civic discourse or spread misinformation</li>
						<li>Claim data as your own without attribution</li>
						<li>Use the service to harass, stalk, or threaten public officials or citizens</li>
					</ul>
				</div>
			</div>
		</section>

		<section id="liability" class="terms-section">
			<h2>Data Accuracy and Liability</h2>
			<p>Engagic provides meeting data <strong>AS-IS</strong> with no warranties. While we strive for accuracy:</p>
			<ul>
				<li>Data is sourced from official government websites but may contain errors - we make every effort to always provide the totality of attachments used to generate the summary, for each item, as well the main overall agenda.</li>
				<li>LLM-generated summaries are AI-assisted and may be imperfect - if you see any deviations or hallucinations, please contact us</li>
				<li>Official meeting packets remain the authoritative source - all information should be double checked on your city's website</li>
				<li>We are not liable for decisions made based on Engagic data - but we sure hope you go out and do good with it</li>
			</ul>
			<p class="warning-text"><strong>Always verify important information</strong> with official government sources before taking action.</p>
		</section>

		<section id="rate-limiting" class="terms-section">
			<h2>Rate Limiting and Enforcement</h2>
			<p>The API enforces rate limits automatically:</p>
			<ul>
				<li><strong>Per-minute limits:</strong> Prevent server overload</li>
				<li><strong>Daily limits:</strong> Ensure fair access for all users</li>
				<li><strong>429 errors:</strong> Returned when limits exceeded</li>
			</ul>
			<p>Repeated rate limit violations or attempts to circumvent limits may result in:</p>
			<ul>
				<li>Temporary IP blocks</li>
				<li>Permanent bans for egregious abuse</li>
				<li>Legal action for damages</li>
			</ul>
			<p class="casual-text">We're reasonable, hit us up.</p>
		</section>

		<section id="changes" class="terms-section">
			<h2>Changes to Terms</h2>
			<p>We may update these terms as the project evolves. Changes will be posted at:</p>
			<ul>
				<li><a href="https://engagic.org/terms" target="_blank" rel="noopener">https://engagic.org/terms</a></li>
				<li><a href="https://github.com/Engagic/engagic/blob/main/docs/TERMS_OF_SERVICE.md" target="_blank" rel="noopener">GitHub Terms of Service</a></li>
			</ul>
			<p>Continued use of the API after changes constitutes acceptance.</p>
		</section>

		<section id="license" class="terms-section">
			<h2>Open Source License</h2>
			<p>The Engagic codebase is licensed under <strong>AGPL-3.0</strong>. This means:</p>
			<ul>
				<li>You can view, modify, and distribute the code</li>
				<li>If you run a modified version as a service, you must make your modifications public</li>
				<li>Commercial use of the code is allowed (see tier requirements for hosted API)</li>
			</ul>
			<p>Full license: <a href="https://github.com/Engagic/engagic/blob/main/LICENSE" target="_blank" rel="noopener">https://github.com/Engagic/engagic/blob/main/LICENSE</a></p>
		</section>

		<section id="contact" class="terms-section">
			<h2>Contact</h2>
			<p><strong>Questions, partnerships, or access requests:</strong></p>
			<div class="contact-links">
				<a href="mailto:hello@engagic.org" class="contact-button">
					<span class="contact-icon">✉</span>
					<span>hello@engagic.org</span>
				</a>
				<a href="https://github.com/Engagic/engagic" target="_blank" rel="noopener" class="contact-button">
					<span class="contact-icon">⚙</span>
					<span>GitHub Repository</span>
				</a>
				<a href="https://github.com/Engagic/engagic/issues" target="_blank" rel="noopener" class="contact-button">
					<span class="contact-icon">⚠</span>
					<span>Report Issues</span>
				</a>
			</div>
		</section>

		<!-- Philosophy Section (highlighted) -->
		<section class="philosophy-section">
			<h2>The Philosophy</h2>
			<p class="philosophy-lead">Civic data should be open. Infrastructure costs money. We're trying to balance both.</p>
			<div class="philosophy-grid">
				<p>If you're an individual wanting to check your city's meetings: <strong>use it freely</strong>.</p>
				<p>If you're a nonprofit fighting for housing justice: <strong>let's partner</strong>.</p>
				<p>If you're a commercial entity building on our work: <strong>let's talk</strong>.</p>
				<p>If you're a VC-backed startup scraping our API to train your models: <strong>pay up or self-host</strong>.</p>
			</div>
			<p class="philosophy-footer">
				<strong>Questions?</strong> <a href="mailto:hello@engagic.org">hello@engagic.org</a><br>
				We're humans. Let's talk.
			</p>
		</section>

		<!-- Back to top -->
		<div class="back-to-top">
			<button onclick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
				↑ Back to Top
			</button>
		</div>
	</main>

	<Footer />
</article>

<style>
	.terms-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-xl);
		padding-bottom: var(--space-xl);
		color: var(--text-primary);
	}

	.page-heading {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2.5rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
		line-height: 1.2;
	}

	.last-updated {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		color: var(--civic-gray);
		margin: 0;
	}

	.back-link {
		position: absolute;
		top: 0;
		left: 0;
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 500;
		transition: color 0.2s ease;
	}

	.back-link:hover {
		text-decoration: underline;
		color: var(--civic-accent);
	}

	/* Table of Contents (cobalt-inspired) */
	.toc {
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		padding: 1.5rem;
		margin-bottom: 3rem;
		box-shadow: 0 2px 8px var(--shadow-sm);
	}

	.toc-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 1rem;
	}

	.toc-list {
		list-style: none;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 0.5rem;
	}

	.toc-list button {
		width: 100%;
		text-align: left;
		background: none;
		border: none;
		color: var(--civic-blue);
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 0.95rem;
		padding: 0.5rem 0.75rem;
		cursor: pointer;
		border-radius: 6px;
		transition: all 0.2s ease;
	}

	.toc-list button:hover {
		background: var(--surface-hover);
		color: var(--civic-accent);
	}

	/* Content Sections - removed center alignment */

	.terms-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}


	.terms-section h2 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.8rem;
		font-weight: 600;
		color: var(--civic-dark);
		margin: 0;
		scroll-margin-top: 2rem;
	}

	.terms-section h3 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.3rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin: 0;
	}

	.terms-section p {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1.1rem;
		line-height: 1.7;
		color: var(--text-primary);
		margin: 0;
	}

	.terms-section ul {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1.1rem;
		line-height: 1.7;
		color: var(--text-primary);
		margin: 0;
		padding-left: 1.5rem;
	}

	.terms-section li {
		margin: 0;
	}

	.terms-section a {
		color: var(--text-link);
		text-decoration: underline;
		transition: color 0.2s ease;
	}

	.terms-section a:hover {
		color: var(--civic-accent);
	}

	/* Tier Cards (cobalt-inspired grid) */
	.tier-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 1.5rem;
	}

	.tier-card {
		background: var(--surface-primary);
		border: 2px solid var(--border-primary);
		border-radius: 12px;
		padding: 1.5rem;
		transition: all 0.3s ease;
	}

	.tier-card:hover {
		transform: translateY(-4px);
		box-shadow: 0 8px 24px var(--shadow-lg);
	}

	.tier-free {
		border-color: var(--civic-green);
	}

	.tier-hacktivist {
		border-color: var(--civic-accent);
	}

	.tier-enterprise {
		border-color: var(--civic-orange);
	}

	.tier-name {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.2rem;
		font-weight: 600;
		margin-bottom: 1rem;
	}

	.tier-free .tier-name {
		color: var(--civic-green);
	}

	.tier-hacktivist .tier-name {
		color: var(--civic-accent);
	}

	.tier-enterprise .tier-name {
		color: var(--civic-orange);
	}

	.tier-limits {
		display: flex;
		align-items: baseline;
		gap: 0.75rem;
		margin-bottom: 1rem;
		padding: 1rem;
		background: var(--surface-secondary);
		border-radius: 8px;
	}

	.limit-item {
		display: flex;
		align-items: baseline;
		gap: 0.25rem;
	}

	.limit-value {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--civic-blue);
	}

	.limit-unit {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-gray);
	}

	.limit-divider {
		color: var(--civic-border);
		font-size: 1.2rem;
	}

	.tier-use-case {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 0.95rem;
		line-height: 1.6;
		color: var(--text-secondary);
		margin-bottom: 1rem;
	}

	.tier-requirements {
		margin: 1rem 0;
	}

	.tier-requirement-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.tier-requirements ul {
		margin-left: 1.5rem;
		font-size: 0.9rem;
	}

	.tier-cost {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin-top: 1rem;
		margin-bottom: 0.5rem;
	}

	.tier-requirement {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 0.9rem;
		color: var(--civic-gray);
		font-style: italic;
	}

	.tier-contact {
		display: inline-block;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		color: var(--civic-blue);
		text-decoration: none;
		padding: 0.5rem 1rem;
		background: var(--surface-secondary);
		border-radius: 6px;
		margin-top: 0.75rem;
		transition: all 0.2s ease;
	}

	.tier-contact:hover {
		background: var(--civic-blue);
		color: var(--civic-white);
	}

	/* Code Blocks (cobalt-inspired) */
	.code-block {
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: 8px;
		padding: 1rem;
		margin: 1rem 0;
		font-family: 'IBM Plex Mono', monospace;
	}

	.code-label {
		font-size: 0.85rem;
		color: var(--civic-gray);
		margin-bottom: 0.5rem;
	}

	.code-block code {
		display: block;
		font-size: 0.95rem;
		color: var(--text-primary);
		line-height: 1.6;
	}

	.code-block a {
		color: var(--civic-blue);
		text-decoration: underline;
	}

	/* Attribution Rules */
	.attribution-rules {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 1.5rem;
		margin-top: 2rem;
	}

	.rule-group {
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		padding: 1.5rem;
	}

	.rule-group h3 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.1rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin-top: 0;
		margin-bottom: 1rem;
	}

	.rule-group ul {
		margin-left: 1.25rem;
		font-size: 0.95rem;
	}

	/* Acceptable Use Policies */
	.use-policies {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
		gap: 1.5rem;
		margin-top: 2rem;
	}

	.policy-allowed,
	.policy-prohibited {
		background: var(--surface-primary);
		border: 2px solid;
		border-radius: 12px;
		padding: 1.5rem;
	}

	.policy-allowed {
		border-color: var(--civic-green);
	}

	.policy-prohibited {
		border-color: var(--civic-red);
	}

	.policy-allowed h3 {
		color: var(--civic-green);
	}

	.policy-prohibited h3 {
		color: var(--civic-red);
	}

	/* Contact Buttons */
	.contact-links {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		margin-top: 1.5rem;
	}

	.contact-button {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1.25rem;
		background: var(--surface-primary);
		border: 2px solid var(--civic-blue);
		border-radius: 8px;
		color: var(--civic-blue);
		text-decoration: none;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.95rem;
		font-weight: 500;
		transition: all 0.3s ease;
	}

	.contact-button:hover {
		background: var(--civic-blue);
		color: var(--civic-white);
		transform: translateY(-2px);
		box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25);
	}

	.contact-icon {
		font-size: 1.2rem;
	}

	/* Text Variants */
	.warning-text {
		color: var(--civic-orange);
		font-weight: 600;
	}

	.casual-text {
		color: var(--civic-gray);
		font-style: italic;
	}

	/* Philosophy Section (highlighted) */
	.philosophy-section {
		background: linear-gradient(135deg, rgba(79, 70, 229, 0.05) 0%, rgba(139, 92, 246, 0.05) 100%);
		border: 2px solid var(--civic-blue);
		border-radius: 12px;
		padding: 2rem;
		margin-top: 4rem;
		margin-bottom: 3rem;
	}

	.philosophy-section h2 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin-bottom: 1rem;
		scroll-margin-top: 2rem;
	}

	.philosophy-lead {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.2rem;
		font-weight: 500;
		color: var(--text-primary);
		margin-bottom: 2rem;
	}

	.philosophy-grid {
		display: grid;
		gap: 1rem;
		margin-bottom: 2rem;
	}

	.philosophy-grid p {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1.1rem;
		line-height: 1.8;
		color: var(--text-secondary);
		padding: 1rem;
		background: var(--surface-primary);
		border-radius: 8px;
		border-left: 4px solid var(--civic-blue);
	}

	.philosophy-footer {
		font-family: Georgia, 'Times New Roman', Times, serif;
		color: var(--text-secondary);
		margin-top: 2rem;
		padding-top: 1.5rem;
		border-top: 1px solid var(--border-primary);
	}

	.philosophy-footer a {
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 600;
	}

	.philosophy-footer a:hover {
		text-decoration: underline;
		color: var(--civic-accent);
	}

	/* Back to Top */
	.back-to-top {
		margin: 3rem 0 2rem;
	}

	.back-to-top button {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.95rem;
		color: var(--civic-blue);
		background: none;
		border: 2px solid var(--civic-blue);
		border-radius: 8px;
		padding: 0.75rem 1.5rem;
		cursor: pointer;
		transition: all 0.3s ease;
	}

	.back-to-top button:hover {
		background: var(--civic-blue);
		color: var(--civic-white);
		transform: translateY(-2px);
	}

	/* Responsive Design (mobile-first) */
	@media (max-width: 640px) {
		.terms-container {
			padding: 2rem 1rem;
		}

		.terms-header h1 {
			font-size: 2rem;
		}

		.back-link {
			position: static;
			display: block;
			margin-bottom: 1rem;
			text-align: left;
		}

		.toc {
			padding: 1rem;
		}

		.toc-list {
			grid-template-columns: 1fr;
		}

		.tier-grid {
			grid-template-columns: 1fr;
		}

		.attribution-rules,
		.use-policies {
			grid-template-columns: 1fr;
		}

		.contact-links {
			flex-direction: column;
		}

		.contact-button {
			width: 100%;
			justify-content: center;
		}

		.philosophy-section {
			padding: 1.5rem;
		}

		.philosophy-lead {
			font-size: 1.05rem;
		}
	}

	@media (max-width: 480px) {
		.limit-item {
			flex-direction: column;
			align-items: flex-start;
		}

		.limit-value {
			font-size: 1.25rem;
		}
	}
</style>

/**
 * Markdown utilities for cleaning LLM-generated content
 */

/**
 * Clean LLM artifacts and markdown headings from summaries
 *
 * Removes:
 * - Markdown headings (## Summary, ## Financial, etc.)
 * - Document section markers
 * - LLM preamble text
 * - Excessive newlines
 */
export function cleanSummary(rawSummary: string): string {
	if (!rawSummary) return '';

	return rawSummary
		.replace(/^##?\s+Summary\s*\n?/im, '')
		.replace(/^##?\s+[^\n]+\n?/gm, '')
		.replace(/=== DOCUMENT \d+ ===/g, '')
		.replace(/--- SECTION \d+ SUMMARY ---/g, '')
		.replace(/Here's a concise summary of the[^:]*:/gi, '')
		.replace(/Here's a summary of the[^:]*:/gi, '')
		.replace(/Here's the key points[^:]*:/gi, '')
		.replace(/Here's a structured analysis[^:]*:/gi, '')
		.replace(/Summary of the[^:]*:/gi, '')
		.replace(/\n{3,}/g, '\n\n')
		.trim();
}

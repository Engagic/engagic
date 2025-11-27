// Input sanitization utilities

const ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'mark'];
const ALLOWED_ATTRS: { [tag: string]: string[] } = {};

export function sanitizeHtml(input: string): string {
	// Basic HTML sanitization - removes script tags and dangerous attributes
	// For production, consider using DOMPurify library
	
	// Remove script tags and their content
	let cleaned = input.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
	
	// Remove on* event handlers
	cleaned = cleaned.replace(/\son\w+\s*=\s*["'][^"']*["']/gi, '');
	
	// Remove javascript: protocol
	cleaned = cleaned.replace(/javascript:/gi, '');
	
	// Remove data: protocol except for images
	cleaned = cleaned.replace(/data:(?!image\/)/gi, '');
	
	return cleaned;
}

export function sanitizeInput(input: string): string {
	// Sanitize user input for display
	return input
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#x27;')
		.replace(/\//g, '&#x2F;');
}

export function validateCityUrl(cityUrl: string): boolean {
	// Validate city URL format: lowercase letters followed by 2 uppercase letters
	return /^[a-z]+[A-Z]{2}$/.test(cityUrl);
}

export function validateZipcode(zipcode: string): boolean {
	// Validate US zipcode format
	return /^\d{5}(-\d{4})?$/.test(zipcode);
}

export function validateSearchQuery(query: string): string | null {
	const trimmed = query.trim();

	if (!trimmed) {
		return 'Please enter a search query';
	}

	if (trimmed.length < 2) {
		return 'Search query must be at least 2 characters';
	}

	if (trimmed.length > 100) {
		return 'Search query is too long';
	}

	// Check for potential injection attempts
	if (/[<>'"\\]/.test(trimmed)) {
		return 'Invalid characters in search query';
	}

	return null; // Valid
}

/**
 * Escape HTML special characters to prevent XSS
 */
export function escapeHtml(text: string): string {
	if (!text) return '';
	return text
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#039;');
}

/**
 * Highlight keyword matches in text with <mark> tags.
 * Escapes HTML first for XSS safety, then wraps matches.
 * Result is safe to use with {@html ...} in Svelte.
 */
export function highlightMatch(context: string, query: string): string {
	if (!context || !query) {
		return escapeHtml(context || '');
	}

	const escapedContext = escapeHtml(context);
	const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
	const regex = new RegExp(`(${escapedQuery})`, 'gi');

	return escapedContext.replace(regex, '<mark>$1</mark>');
}

/**
 * Extract a snippet from text centered around a keyword
 */
export function extractSnippet(
	text: string,
	keyword: string,
	snippetLength: number = 300
): string {
	if (!text) return '';
	if (!keyword) return text.slice(0, snippetLength) + (text.length > snippetLength ? '...' : '');

	const textLower = text.toLowerCase();
	const keywordLower = keyword.toLowerCase();

	const pos = textLower.indexOf(keywordLower);
	if (pos === -1) {
		return text.slice(0, snippetLength) + (text.length > snippetLength ? '...' : '');
	}

	const halfLength = Math.floor(snippetLength / 2);
	let start = Math.max(0, pos - halfLength);
	let end = Math.min(text.length, pos + keyword.length + halfLength);

	if (start > 0) {
		const spacePos = text.lastIndexOf(' ', start + 20);
		if (spacePos > start - 20) {
			start = spacePos + 1;
		}
	}

	if (end < text.length) {
		const spacePos = text.indexOf(' ', end - 20);
		if (spacePos !== -1 && spacePos < end + 20) {
			end = spacePos;
		}
	}

	let snippet = text.slice(start, end);

	if (start > 0) {
		snippet = '...' + snippet;
	}
	if (end < text.length) {
		snippet = snippet + '...';
	}

	return snippet;
}
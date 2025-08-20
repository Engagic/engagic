// Input sanitization utilities

const ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'blockquote'];
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
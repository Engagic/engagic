/**
 * Anchor ID generation utilities
 *
 * Consistent anchor ID generation across agenda items, matter timelines, and deep linking.
 * Priority hierarchy:
 * 1. agenda_number (meeting-specific position, e.g., "5-E" → "item-5-e")
 * 2. matter_file (legislative file number, e.g., "2025-5470" → "2025-5470")
 * 3. item_id (fallback unique identifier)
 */

interface AnchorableItem {
	id?: string;
	agenda_number?: string;
	matter_file?: string;
}

/**
 * Generate anchor ID for an agenda item or timeline appearance
 *
 * @param item - Object with optional id, agenda_number, and/or matter_file
 * @returns Anchor ID string suitable for HTML id attributes and URL fragments
 *
 * @example
 * generateAnchorId({ agenda_number: '5-E' })          // "item-5-e"
 * generateAnchorId({ matter_file: '2025-5470' })      // "2025-5470"
 * generateAnchorId({ id: '123' })                     // "item-123"
 */
export function generateAnchorId(item: AnchorableItem): string {
	// Priority 1: agenda_number (meeting-specific position)
	if (item.agenda_number) {
		const normalized = item.agenda_number
			.toLowerCase()
			.replace(/[^a-z0-9]/g, '-')  // Replace non-alphanumeric with hyphens
			.replace(/-+/g, '-')         // Collapse multiple hyphens
			.replace(/^-|-$/g, '');      // Trim leading/trailing hyphens
		return `item-${normalized}`;
	}

	// Priority 2: matter_file (legislative identifier)
	if (item.matter_file) {
		const normalized = item.matter_file
			.toLowerCase()
			.replace(/[^a-z0-9-]/g, '-'); // Keep hyphens, replace other non-alphanumeric
		return normalized;
	}

	// Priority 3: item ID (fallback)
	return `item-${item.id}`;
}

/**
 * Find matching item by anchor hash
 *
 * Gracefully matches ALL possible anchor formats for an item:
 * - agenda_number format (primary): "item-5-e"
 * - matter_file format (fallback): "bl2025-1098"
 * - item.id format (final fallback): "item-abc123"
 *
 * @param items - Array of items to search
 * @param hash - URL hash (with or without leading #)
 * @returns Matching item or undefined
 *
 * @example
 * findItemByAnchor(items, '#item-5-e')      // matches agenda_number
 * findItemByAnchor(items, 'bl2025-1098')    // matches matter_file
 * findItemByAnchor(items, 'item-abc123')    // matches item.id
 */
export function findItemByAnchor<T extends AnchorableItem>(
	items: T[],
	hash: string
): T | undefined {
	// Remove leading # if present
	const normalizedHash = hash.startsWith('#') ? hash.substring(1) : hash;

	return items.find(item => {
		// Check all possible anchor formats for this item
		const possibleAnchors: string[] = [];

		// Format 1: agenda_number (if present)
		if (item.agenda_number) {
			const normalized = item.agenda_number
				.toLowerCase()
				.replace(/[^a-z0-9]/g, '-')
				.replace(/-+/g, '-')
				.replace(/^-|-$/g, '');
			possibleAnchors.push(`item-${normalized}`);
		}

		// Format 2: matter_file (if present)
		if (item.matter_file) {
			const normalized = item.matter_file
				.toLowerCase()
				.replace(/[^a-z0-9-]/g, '-');
			possibleAnchors.push(normalized);
		}

		// Format 3: item.id (always present as fallback)
		if (item.id) {
			possibleAnchors.push(`item-${item.id}`);
		}

		// Match if hash equals any possible anchor format
		return possibleAnchors.includes(normalizedHash);
	});
}

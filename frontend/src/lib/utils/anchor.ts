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
 * @param items - Array of items to search
 * @param hash - URL hash (with or without leading #)
 * @returns Matching item or undefined
 *
 * @example
 * findItemByAnchor(items, '#item-5-e')
 * findItemByAnchor(items, '2025-5470')
 */
export function findItemByAnchor<T extends AnchorableItem>(
	items: T[],
	hash: string
): T | undefined {
	// Remove leading # if present
	const normalizedHash = hash.startsWith('#') ? hash.substring(1) : hash;

	return items.find(item => {
		const anchorId = generateAnchorId(item);
		return anchorId === normalizedHash;
	});
}

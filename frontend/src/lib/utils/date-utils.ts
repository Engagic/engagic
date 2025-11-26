// Centralized date formatting utilities

/**
 * Format a date relative to now for conversational display
 *
 * Examples:
 * - "Tomorrow at 6pm"
 * - "Thursday at 7pm"
 * - "Nov 28 at 2pm"
 * - "In 2 hours"
 */
export function formatRelativeTime(dateString: string | null): string {
	if (!dateString || dateString === 'null' || dateString === '') {
		return 'Date TBD';
	}

	const date = new Date(dateString);
	if (isNaN(date.getTime())) {
		return 'Date TBD';
	}

	const now = new Date();
	const diffMs = date.getTime() - now.getTime();
	const diffHours = diffMs / (1000 * 60 * 60);
	const diffDays = diffMs / (1000 * 60 * 60 * 24);

	const timeStr = date.toLocaleTimeString('en-US', {
		hour: 'numeric',
		minute: date.getMinutes() > 0 ? '2-digit' : undefined,
		hour12: true
	}).toLowerCase();

	// Within the next 4 hours
	if (diffHours > 0 && diffHours <= 4) {
		const hours = Math.round(diffHours);
		return hours === 1 ? 'In 1 hour' : `In ${hours} hours`;
	}

	// Today
	if (isToday(date)) {
		return `Today at ${timeStr}`;
	}

	// Tomorrow
	if (isTomorrow(date)) {
		return `Tomorrow at ${timeStr}`;
	}

	// Within the next 7 days - use day name
	if (diffDays > 0 && diffDays <= 7) {
		const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
		return `${dayNames[date.getDay()]} at ${timeStr}`;
	}

	// Further out - use date
	const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	return `${months[date.getMonth()]} ${date.getDate()} at ${timeStr}`;
}

/**
 * Get urgency level for a meeting date
 * Returns: 'urgent' (<24h), 'soon' (<72h), 'upcoming' (<168h), or 'future'
 */
export function getUrgencyLevel(dateString: string | null): 'urgent' | 'soon' | 'upcoming' | 'future' | 'past' {
	if (!dateString) return 'future';

	const date = new Date(dateString);
	if (isNaN(date.getTime())) return 'future';

	const now = new Date();
	const diffHours = (date.getTime() - now.getTime()) / (1000 * 60 * 60);

	if (diffHours < 0) return 'past';
	if (diffHours <= 24) return 'urgent';
	if (diffHours <= 72) return 'soon';
	if (diffHours <= 168) return 'upcoming';
	return 'future';
}

/**
 * Check if a date is today
 */
function isToday(date: Date): boolean {
	const today = new Date();
	return date.getDate() === today.getDate() &&
		date.getMonth() === today.getMonth() &&
		date.getFullYear() === today.getFullYear();
}

/**
 * Check if a date is tomorrow
 */
function isTomorrow(date: Date): boolean {
	const tomorrow = new Date();
	tomorrow.setDate(tomorrow.getDate() + 1);
	return date.getDate() === tomorrow.getDate() &&
		date.getMonth() === tomorrow.getMonth() &&
		date.getFullYear() === tomorrow.getFullYear();
}

/**
 * Format hours until a meeting for API responses
 * Returns a human-readable string like "2 hours", "1 day", "3 days"
 */
export function formatHoursUntil(hours: number | null): string {
	if (hours === null || hours < 0) return '';

	if (hours < 1) {
		const minutes = Math.round(hours * 60);
		return minutes <= 1 ? '1 min' : `${minutes} mins`;
	}

	if (hours < 24) {
		const h = Math.round(hours);
		return h === 1 ? '1 hour' : `${h} hours`;
	}

	const days = Math.round(hours / 24);
	return days === 1 ? '1 day' : `${days} days`;
}

export function formatMeetingDate(dateString: string | null): string {
	if (!dateString || dateString === 'null' || dateString === '') {
		return 'Date TBD';
	}

	const date = new Date(dateString);

	if (isNaN(date.getTime()) || date.getTime() === 0) {
		return 'Date TBD';
	}

	const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	const monthName = months[date.getMonth()];
	const day = date.getDate();
	const year = date.getFullYear();

	return `${monthName} ${day}, ${year}`;
}

export function extractTime(dateString: string | null): string {
	if (!dateString || dateString === 'null' || dateString === '') {
		return '';
	}

	const date = new Date(dateString);

	if (isNaN(date.getTime()) || date.getTime() === 0) {
		return '';
	}

	return date.toLocaleTimeString('en-US', {
		hour: 'numeric',
		minute: '2-digit',
		hour12: true
	});
}

export function formatMeetingDateLong(dateString: string | null): string {
	if (!dateString || dateString === 'null' || dateString === '') {
		return 'Date TBD';
	}

	const date = new Date(dateString);

	if (isNaN(date.getTime()) || date.getTime() === 0) {
		return 'Date TBD';
	}

	const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	const monthName = months[date.getMonth()];
	const day = date.getDate();
	const year = date.getFullYear();

	const suffix = day === 1 || day === 21 || day === 31 ? 'st' :
				  day === 2 || day === 22 ? 'nd' :
				  day === 3 || day === 23 ? 'rd' : 'th';

	return `${monthName} ${day}${suffix}, ${year}`;
}
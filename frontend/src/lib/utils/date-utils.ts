// Centralized date formatting utilities

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
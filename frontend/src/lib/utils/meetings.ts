import type { Meeting } from '$lib/api/types';

/**
 * Sorts meetings by date (soonest first).
 * Meetings without valid dates are placed at the end.
 */
export function sortMeetingsByDate(meetings: Meeting[]): Meeting[] {
	return meetings.sort((a, b) => {
		const dateA = a.date ? new Date(a.date) : new Date(9999, 11, 31);
		const dateB = b.date ? new Date(b.date) : new Date(9999, 11, 31);
		return dateA.getTime() - dateB.getTime();
	});
}

/**
 * Splits meetings into upcoming and past based on current time.
 * Meetings persist as "upcoming" for 6 hours after their start time
 * (since meetings typically last a few hours).
 * Meetings with invalid/missing dates are considered upcoming.
 */
export function splitMeetingsByDate(meetings: Meeting[]): {
	upcoming: Meeting[];
	past: Meeting[];
} {
	const now = new Date();
	// 6 hours in milliseconds - meetings stay "upcoming" for this long after start
	const MEETING_DURATION_MS = 6 * 60 * 60 * 1000;

	const upcoming: Meeting[] = [];
	const past: Meeting[] = [];

	for (const meeting of meetings) {
		if (!meeting.date || meeting.date === 'null' || meeting.date === '') {
			// Meetings with no date go to upcoming
			upcoming.push(meeting);
			continue;
		}

		const meetingDate = new Date(meeting.date);

		// Skip invalid dates (NaN or epoch 0)
		if (isNaN(meetingDate.getTime()) || meetingDate.getTime() === 0) {
			upcoming.push(meeting);
			continue;
		}

		// Meeting is upcoming if current time is before (start time + 6 hours)
		const meetingEndTime = meetingDate.getTime() + MEETING_DURATION_MS;
		if (now.getTime() < meetingEndTime) {
			upcoming.push(meeting);
		} else {
			past.push(meeting);
		}
	}

	return { upcoming, past };
}

/**
 * Sorts and splits meetings in a single operation.
 * Convenience function that combines sortMeetingsByDate and splitMeetingsByDate.
 */
export function processMeetingDates(meetings: Meeting[]): {
	upcoming: Meeting[];
	past: Meeting[];
} {
	const sorted = sortMeetingsByDate(meetings);
	return splitMeetingsByDate(sorted);
}

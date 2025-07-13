const API_BASE = 'https://api.engagic.org';

export interface CityOption {
	city_name: string;
	state: string;
	city_banana: string;
	vendor: string;
	display_name: string;
}

export interface SearchResult {
	success: boolean;
	city_name?: string;
	state?: string;
	city_banana?: string;
	vendor?: string;
	meetings?: Meeting[];
	message?: string;
	cached?: boolean;
	query?: string;
	type?: string;
	ambiguous?: boolean;
	city_options?: CityOption[];
}

export interface Meeting {
	meeting_id?: string;
	title?: string;
	start?: string;
	packet_url?: string;
	meeting_name?: string;
	meeting_date?: string;
}

export interface CachedSummary {
	success: boolean;
	summary?: string;
	cached?: boolean;
	meeting_data?: {
		packet_url?: string | string[];
		[key: string]: any;
	};
	error?: string;
}

export async function searchMeetings(query: string): Promise<SearchResult> {
	try {
		const response = await fetch(`${API_BASE}/api/search`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({ query }),
		});

		if (!response.ok) {
			if (response.status === 429) {
				throw new Error('Too many requests. Please wait a moment and try again.');
			} else if (response.status === 500) {
				throw new Error('We humbly thank you for your patience');
			} else if (response.status === 404) {
				throw new Error('No meetings found for this location');
			}
			throw new Error('We humbly thank you for your patience');
		}

		return response.json();
	} catch (error) {
		// Network errors (fetch failures)
		if (error instanceof TypeError && error.message.includes('fetch')) {
			throw new Error('We humbly thank you for your patience');
		}
		throw error;
	}
}

export async function getCachedSummary(meeting: Meeting, cityBanana: string): Promise<CachedSummary> {
	try {
		const response = await fetch(`${API_BASE}/api/process-agenda`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({
				packet_url: meeting.packet_url,
				city_banana: cityBanana,
				meeting_name: meeting.title || meeting.meeting_name,
				meeting_date: meeting.start || meeting.meeting_date,
				meeting_id: meeting.meeting_id,
			}),
		});

		if (!response.ok) {
			if (response.status === 429) {
				throw new Error('Too many requests. Please wait a moment and try again.');
			} else if (response.status === 500) {
				throw new Error('We humbly thank you for your patience');
			} else if (response.status === 404) {
				throw new Error('No agendas posted yet, please come back later! Packets are typically posted within 48 hours of the meeting date');
			}
			throw new Error('No agendas posted yet, please come back later! Packets are typically posted within 48 hours of the meeting date');
		}

		const result = await response.json();
		
		// Check if the response indicates no summary is available yet
		if (!result.success && result.message && result.message.includes('not yet available')) {
			throw new Error('No agendas posted yet, please come back later! Packets are typically posted within 48 hours of the meeting date');
		}
		
		return result;
	} catch (error) {
		// Network errors (fetch failures)
		if (error instanceof TypeError && error.message.includes('fetch')) {
			throw new Error('We humbly thank you for your patience');
		}
		throw error;
	}
}
const API_BASE = 'https://api.engagic.org';

export interface CityOption {
	city_name: string;
	state: string;
	city_slug: string;
	vendor: string;
	display_name: string;
}

export interface SearchResult {
	success: boolean;
	city_name?: string;
	state?: string;
	city_slug?: string;
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

export interface ProcessResult {
	success: boolean;
	summary?: string;
	processing_time_seconds?: number;
	cached?: boolean;
	meeting_data?: any;
	error?: string;
}

export async function searchMeetings(query: string): Promise<SearchResult> {
	const response = await fetch(`${API_BASE}/api/search`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
		},
		body: JSON.stringify({ query }),
	});

	if (!response.ok) {
		throw new Error(`Search failed: ${response.status}`);
	}

	return response.json();
}

export async function processAgenda(meeting: Meeting, citySlug: string): Promise<ProcessResult> {
	const response = await fetch(`${API_BASE}/api/process-agenda`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
		},
		body: JSON.stringify({
			packet_url: meeting.packet_url,
			city_slug: citySlug,
			meeting_name: meeting.title || meeting.meeting_name,
			meeting_date: meeting.start || meeting.meeting_date,
			meeting_id: meeting.meeting_id,
		}),
	});

	if (!response.ok) {
		throw new Error(`Processing failed: ${response.status}`);
	}

	return response.json();
}
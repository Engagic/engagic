// Discriminated unions for better type safety

export interface CityOption {
	city_name: string;
	state: string;
	banana: string;
	vendor: string;
	display_name: string;
	total_meetings: number;
	meetings_with_packet: number;
	summarized_meetings: number;
}

export interface Meeting {
	banana: string;
	title: string;
	date: string; // ISO format datetime
	packet_url?: string | string[];
	summary?: string;
	meeting_status?: 'cancelled' | 'postponed' | 'revised' | 'rescheduled' | 'deferred';
}

export interface RandomMeetingResponse {
	status: string;
	meeting: {
		banana: string;
		title: string;
		date: string;
		packet_url: string;
		summary: string;
		quality_score: number;
	};
}

// Discriminated union for search results
export type SearchResult = 
	| SearchSuccess
	| SearchAmbiguous
	| SearchError;

interface SearchSuccess {
	success: true;
	city_name: string;
	state: string;
	banana: string;
	vendor: string;
	meetings: Meeting[];
	cached: boolean;
	query: string;
	type: 'city' | 'zipcode';
}

interface SearchAmbiguous {
	success: false;
	ambiguous: true;
	message: string;
	city_options: CityOption[];
	query: string;
}

interface SearchError {
	success: false;
	ambiguous?: false;
	message: string;
	query?: string;
}

export interface AnalyticsData {
	success: boolean;
	timestamp: string;
	real_metrics: {
		cities_covered: number;
		meetings_tracked: number;
		meetings_with_packet: number;
		agendas_summarized: number;
		states_covered: number;
		zipcodes_served: number;
		active_cities: number;
	};
}

// Error types
export class ApiError extends Error {
	constructor(
		message: string,
		public statusCode: number,
		public isRetryable: boolean = false
	) {
		super(message);
		this.name = 'ApiError';
	}
}

export class NetworkError extends Error {
	constructor(message: string) {
		super(message);
		this.name = 'NetworkError';
	}
}

// Type guards
export function isSearchSuccess(result: SearchResult): result is SearchSuccess {
	return result.success === true;
}

export function isSearchAmbiguous(result: SearchResult): result is SearchAmbiguous {
	return result.success === false && result.ambiguous === true;
}

export function isSearchError(result: SearchResult): result is SearchError {
	return result.success === false && !result.ambiguous;
}
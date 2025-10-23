// Discriminated unions for better type safety

export interface CityOption {
	city_name: string;
	state: string;
	city_banana: string;
	vendor: string;
	display_name: string;
	total_meetings: number;
	summarized_meetings: number;
}

export interface Meeting {
	id: string;
	city_banana: string;
	title: string;
	date: string; // ISO format datetime
	packet_url?: string | string[];
	summary?: string;
	processing_status?: string;
	processing_method?: string;
	processing_time?: number;
	created_at?: string;
	updated_at?: string;
}

export interface RandomMeetingResponse {
	status: string;
	meeting: {
		id: number;
		city_banana: string;
		meeting_name: string;
		meeting_date: string;
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
	city_banana: string;
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

// API response types
export interface CachedSummary {
	success: boolean;
	summary?: string;
	cached?: boolean;
	meeting_data?: {
		packet_url?: string | string[];
		meeting_name?: string;
		meeting_date?: string;
		meeting_id?: string;
	};
	error?: string;
}

export interface AnalyticsData {
	success: boolean;
	timestamp: string;
	headline_metrics: {
		cities_covered: number;
		meetings_tracked: number;
		agendas_summarized: number;
		states_covered: number;
		zipcodes_served: number;
	};
	quality_metrics: {
		active_cities: number;
	};
	real_metrics: {
		cities_covered: number;
		meetings_tracked: number;
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
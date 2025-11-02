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

export interface AgendaItem {
	id: string;
	meeting_id: string;
	title: string;
	sequence: number;
	attachments: Array<{
		url?: string;
		pages?: string;
		name?: string;
		type?: string;
	}>;
	summary?: string;
	topics?: string[];
	created_at?: string;
}

export interface Meeting {
	id?: string;
	banana: string;
	title: string;
	date: string; // ISO format datetime
	agenda_url?: string; // HTML/PDF agenda with extracted items (item-based, primary)
	packet_url?: string | string[]; // Monolithic PDF fallback (no items extracted)
	summary?: string;
	meeting_status?: 'cancelled' | 'postponed' | 'revised' | 'rescheduled';
	participation?: {
		email?: string;
		phone?: string;
		virtual_url?: string;
		meeting_id?: string;
		is_hybrid?: boolean;
		is_virtual_only?: boolean;
		physical_location?: string;
	};
	topics?: string[];
	processing_status?: 'pending' | 'processing' | 'completed' | 'failed';
	has_items?: boolean; // True for item-based meetings, false for monolithic
	items?: AgendaItem[]; // Present for item-based meetings (58% of cities)
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

export interface RandomMeetingWithItemsResponse {
	success: boolean;
	meeting: {
		id: number;
		banana: string;
		title: string;
		date: string;
		packet_url: string;
		item_count: number;
		avg_summary_length: number;
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
	type: 'city' | 'zipcode' | 'state';
}

interface SearchAmbiguous {
	success: boolean;  // Can be true (state search found cities) or false (city not found)
	ambiguous: true;
	message: string;
	city_options: CityOption[];
	query: string;
	type?: 'city' | 'state';
	meetings?: Meeting[];
}

interface SearchError {
	success: false;
	ambiguous?: false;
	message: string;
	query?: string;
}

// Topic search types
export interface TopicSearchRequest {
	topic: string;
	banana?: string;
	limit?: number;
}

export interface TopicSearchResult {
	success: boolean;
	query: string;
	normalized_topic: string;
	display_name?: string;
	results: Array<{
		meeting: Meeting;
		matching_items?: AgendaItem[];
	}>;
	count: number;
	banana?: string;
	city_name?: string;
	state?: string;
}

export interface AnalyticsData {
	success: boolean;
	timestamp: string;
	real_metrics: {
		cities_covered: number;
		meetings_tracked: number;
		meetings_with_packet: number;
		agendas_summarized: number;
		active_cities: number;
	};
}

export interface TickerItem {
	city: string;
	date: string;
	excerpt: string;
	url: string;
}

export interface TickerResponse {
	success: boolean;
	items: TickerItem[];
	count: number;
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
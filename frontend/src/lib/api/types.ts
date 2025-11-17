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
	// Matter tracking (Nov 2025)
	matter_id?: string;  // Backend unique identifier
	matter_file?: string;  // Official public identifier (BL2025-1005, 25-1209, etc.)
	matter_type?: string;  // Ordinance, Resolution, CD 12, etc.
	agenda_number?: string;  // Position on this agenda (1, K. 87, etc.)
	sponsors?: string[];  // Sponsor names
	matter?: Matter;  // Eagerly loaded Matter object (when load_matters=True in API)
}

export interface Meeting {
	id: string;
	banana: string;
	title: string;
	date: string | null; // ISO format datetime or null when missing
	agenda_url?: string; // HTML/PDF agenda with extracted items (item-based, primary)
	packet_url?: string | string[]; // Monolithic PDF fallback (no items extracted)
	summary?: string;
	meeting_status?: 'cancelled' | 'postponed' | 'revised' | 'rescheduled';
	participation?: {
		email?: string;
		emails?: Array<{
			address: string;
			purpose: string;
		}>;
		phone?: string;
		virtual_url?: string;
		meeting_id?: string;
		streaming_urls?: Array<{
			url?: string;
			platform: string;
			channel?: string;
		}>;
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
		id: string;
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
		id: string;
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
		active_cities: number;
		meetings_tracked: number;
		meetings_with_items: number;
		meetings_with_packet: number;
		agendas_summarized: number;
		agenda_items_processed: number;
		matters_tracked: number;
		unique_item_summaries: number;
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

// Flyer generation types (mirrors backend Pydantic models)
export type FlyerPosition = 'support' | 'oppose' | 'more_info';

export interface FlyerRequest {
	meeting_id: string;
	item_id: string | null;
	position: FlyerPosition;
	custom_message: string | null;
	user_name: string | null;
}

export interface FlyerConstraints {
	readonly MAX_MESSAGE_LENGTH: 500;
	readonly MAX_NAME_LENGTH: 100;
	readonly POSITIONS: readonly FlyerPosition[];
}

export const FLYER_CONSTRAINTS: FlyerConstraints = {
	MAX_MESSAGE_LENGTH: 500,
	MAX_NAME_LENGTH: 100,
	POSITIONS: ['support', 'oppose', 'more_info'] as const,
} as const;

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

// Matter types
export interface Matter {
	id: string;
	matter_file?: string;
	matter_type?: string;
	title: string;
	canonical_summary?: string;
	canonical_topics?: string[];
	sponsors?: string[];
	attachments?: Array<{ name: string; url: string; type: string }>;
	first_seen: string;
	last_seen: string;
	appearance_count?: number;  // Number of times this matter appeared across meetings
}

export interface MatterTimelineAppearance {
	item_id: string;
	meeting_id: string;
	meeting_title: string;
	meeting_date: string;
	city_name: string;
	state: string;
	banana: string;
	agenda_number?: string;
	summary?: string;
	topics?: string[];
}

export interface MatterTimelineResponse {
	success: boolean;
	matter: Matter;
	timeline: MatterTimelineAppearance[];
	appearance_count: number;
}

export interface GetMeetingResponse {
	success: boolean;
	meeting: Meeting;
	city_name: string | null;
	state: string | null;
	banana: string;
}

export interface MatterSummary {
	id: string;
	matter_file?: string;
	matter_type?: string;
	title: string;
	canonical_summary?: string;
	canonical_topics?: string;
	appearance_count: number;
	first_seen: string;
	last_seen: string;
}

export interface GetCityMattersResponse {
	success: boolean;
	city_name: string;
	state: string;
	banana: string;
	matters: MatterSummary[];
	total_count: number;
	limit: number;
	offset: number;
}

export interface StateMatterSummary {
	id: string;
	matter_file?: string;
	matter_type?: string;
	title: string;
	canonical_summary?: string;
	canonical_topics?: string;
	appearance_count: number;
	first_seen: string;
	last_seen: string;
	city_name: string;
	banana: string;
	state: string;
}

export interface GetStateMattersResponse {
	success: boolean;
	state: string;
	cities_count: number;
	cities: Array<{
		banana: string;
		name: string;
		vendor: string;
	}>;
	matters: StateMatterSummary[];
	total_matters: number;
	topic_distribution: Record<string, number>;
	filtered_by_topic?: string;
	meeting_stats: {
		total_meetings: number;
		with_agendas: number;
		with_summaries: number;
	};
}
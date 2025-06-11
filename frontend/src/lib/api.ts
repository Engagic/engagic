export interface Meeting {
    meeting_id?: number;
    id?: number;
    title?: string;
    meeting_name?: string;
    start?: string;
    meeting_date?: string;
    packet_url: string;
}

export interface RecentAgenda {
    id: number;
    city: string;
    date: string;
    title: string;
    summary: string;
    urgent: boolean;
    packet_url?: string;
}

/**
 * Information returned by the unified search endpoint.
 * Includes vendor metadata and any cached meetings for the city.
 */
export interface SearchResult {
    zipcode?: string;
    city: string;
    city_slug: string;
    state?: string;
    county?: string;
    vendor: string;
    meetings: Meeting[];
    is_new_city?: boolean;
    needs_manual_config?: boolean;
}

// Production API endpoint with SSL certificate
const API_BASE_URL = 'https://api.engagic.org';

export class ApiService {

    static async getMeetings(city_slug: string): Promise<Meeting[]> {
        try {
            console.log(`Fetching: ${API_BASE_URL}/api/meetings?city=${city_slug}`);
            const response = await fetch(`${API_BASE_URL}/api/meetings?city=${city_slug}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
            });
            
            if (!response.ok) {
                throw new Error(`API request failed: ${response.status} ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('Error fetching meetings:', error);
            throw error;
        }
    }

    static async searchMeetings(searchInput: string): Promise<SearchResult> {
        const normalized = searchInput.trim();
        
        try {
            console.log(`Searching: ${API_BASE_URL}/api/search/${encodeURIComponent(normalized)}`);
            const response = await fetch(`${API_BASE_URL}/api/search/${encodeURIComponent(normalized)}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
            });
            
            if (!response.ok) {
                throw new Error(`Search failed: ${response.status} ${response.statusText}`);
            }
            
            const result = await response.json();
            
            return result;
        } catch (error) {
            throw new Error(`No results found for "${normalized}": ${error}`);
        }
    }
}
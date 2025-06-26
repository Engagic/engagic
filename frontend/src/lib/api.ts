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
    status?: string;
    message?: string;
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
                signal: AbortSignal.timeout(10000) // 10 second timeout
            });
            
            if (!response.ok) {
                let errorMessage = 'Failed to load meetings';
                
                try {
                    const errorData = await response.json();
                    errorMessage = errorData.detail || errorMessage;
                } catch {
                    errorMessage = `${response.status} ${response.statusText}`;
                }
                
                throw new Error(errorMessage);
            }
            
            const result = await response.json();
            console.log('Meetings result:', result);
            
            return result;
        } catch (error) {
            console.error('Error fetching meetings:', error);
            if (error instanceof Error) {
                if (error.name === 'AbortError') {
                    throw new Error('Request timed out. Please try again.');
                }
                if (error.message.includes('Failed to fetch')) {
                    throw new Error('Network error. Please check your connection.');
                }
                throw error;
            }
            throw new Error(`Failed to load meetings: ${error}`);
        }
    }

    static async searchMeetings(searchInput: string): Promise<SearchResult> {
        const normalized = searchInput.trim();
        
        if (!normalized) {
            throw new Error('Please enter a zipcode or city name');
        }
        
        try {
            console.log(`Searching: ${API_BASE_URL}/api/search/${encodeURIComponent(normalized)}`);
            const response = await fetch(`${API_BASE_URL}/api/search/${encodeURIComponent(normalized)}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
                // Add timeout
                signal: AbortSignal.timeout(15000) // 15 second timeout
            });
            
            if (!response.ok) {
                let errorMessage = 'Search failed';
                
                try {
                    const errorData = await response.json();
                    errorMessage = errorData.detail || errorMessage;
                } catch {
                    // If we can't parse the error response, use status text
                    errorMessage = `${response.status} ${response.statusText}`;
                }
                
                throw new Error(errorMessage);
            }
            
            const result = await response.json();
            console.log('Search result:', result);
            
            return result;
        } catch (error) {
            if (error instanceof Error) {
                if (error.name === 'AbortError') {
                    throw new Error('Search timed out. Please try again.');
                }
                if (error.message.includes('Failed to fetch')) {
                    throw new Error('Network error. Please check your connection and try again.');
                }
                throw error;
            }
            throw new Error(`Search failed: ${error}`);
        }
    }
}
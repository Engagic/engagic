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
 * Information returned when looking up a zipcode.
 * Includes vendor metadata and any cached meetings for the city.
 */
export interface ZipcodeLookupResult {
    zipcode: string;
    city: string;
    city_slug: string;
    state: string;
    county: string;
    vendor: string;
    meetings: Meeting[];
}

const API_BASE_URL = 'http://165.232.158.241:8000';

export class ApiService {
    /**
     * Resolve a zipcode to city information.
     *
     * The API response also provides the packet vendor for the city and any
     * cached meetings that were discovered during the lookup.
     */
    static async lookupZipcode(zipcode: string): Promise<ZipcodeLookupResult> {
        try {
            console.log(`Fetching: ${API_BASE_URL}/api/zipcode-lookup/${zipcode}`);
            const response = await fetch(`${API_BASE_URL}/api/zipcode-lookup/${zipcode}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
            });
            
            if (!response.ok) {
                throw new Error(`Zipcode lookup failed: ${response.status} ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('Error looking up zipcode:', error);
            throw error;
        }
    }

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

    static async searchMeetings(searchInput: string): Promise<{meetings: Meeting[], city: string, city_slug: string, zipcode: string, vendor: string}> {
        const normalized = searchInput.trim();
        
        // Only accept zipcode input (5 digits)
        if (!/^\d{5}$/.test(normalized)) {
            throw new Error(`Please enter a 5-digit zipcode.`);
        }
        
        try {
            const zipcodeResult = await this.lookupZipcode(normalized);
            const meetings = await this.getMeetings(zipcodeResult.city_slug);
            
            return {
                meetings,
                city: zipcodeResult.city,
                city_slug: zipcodeResult.city_slug,
                zipcode: zipcodeResult.zipcode,
                vendor: zipcodeResult.vendor
            };
        } catch (error) {
            throw new Error(`No meetings found for "${normalized}", error is "${error}".`);
        }
    }

    static formatMeetingAsAgenda(meeting: Meeting, city: string): RecentAgenda {
        // Handle both API response format and database format
        const meetingDate = meeting.start || meeting.meeting_date;
        const meetingTitle = meeting.title || meeting.meeting_name || 'Untitled Meeting';
        const meetingId = meeting.meeting_id || meeting.id || 0;
        
        // Convert ISO date to readable format
        const date = new Date(meetingDate || '');
        const formattedDate = date.toISOString().split('T')[0]; // YYYY-MM-DD format
        
        // Determine urgency based on date (meetings within 3 days)
        const daysUntilMeeting = Math.ceil((date.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
        const urgent = daysUntilMeeting <= 3 && daysUntilMeeting >= 0;
        
        return {
            id: meetingId,
            city: city,
            date: formattedDate,
            title: meetingTitle,
            summary: meetingTitle,
            urgent,
            packet_url: meeting.packet_url
        };
    }


}
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

const API_BASE_URL = 'https://165.232.158.241:8000';

export class ApiService {
    static async lookupZipcode(zipcode: string): Promise<{zipcode: string, city: string, city_slug: string, state: string, county: string}> {
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

    static async searchMeetings(searchInput: string): Promise<{meetings: Meeting[], city: string, city_slug: string, zipcode: string}> {
        const normalized = searchInput.trim();
        
        try {
            const zipcodeResult = await this.lookupZipcode(normalized);
            const meetings = await this.getMeetings(zipcodeResult.city_slug);
            
            return {
                meetings,
                city: zipcodeResult.city,
                city_slug: zipcodeResult.city_slug,
                zipcode: zipcodeResult.zipcode
            };
        } catch (error) {
            throw new Error(`No meetings found for "${normalized}", error is "${error}" .);
        }
    }
}
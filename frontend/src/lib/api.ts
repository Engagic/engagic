export interface Meeting {
    meeting_id: number;
    title: string;
    start: string;
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

// TODO: Replace with your actual DigitalOcean droplet domain
// Example: https://your-droplet-ip-or-domain.com
const API_BASE_URL = 'http://http://165.232.158.241:8000'; // Update this to your droplet URL

export class ApiService {
    static async getMeetings(city: string = 'cityofpaloalto'): Promise<Meeting[]> {
        try {
            const response = await fetch(`${API_BASE_URL}/api/meetings?city=${encodeURIComponent(city)}`);
            
            if (!response.ok) {
                throw new Error(`API request failed: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('Error fetching meetings:', error);
            throw error;
        }
    }

    static formatMeetingAsAgenda(meeting: Meeting, city: string): RecentAgenda {
        // Convert ISO date to readable format
        const date = new Date(meeting.start);
        const formattedDate = date.toISOString().split('T')[0]; // YYYY-MM-DD format
        
        // Determine urgency based on date (meetings within 3 days)
        const daysUntilMeeting = Math.ceil((date.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
        const urgent = daysUntilMeeting <= 3 && daysUntilMeeting >= 0;
        
        return {
            id: meeting.meeting_id,
            city: this.formatCityName(city),
            date: formattedDate,
            title: meeting.title,
            summary: this.generateSummary(meeting.title),
            urgent,
            packet_url: meeting.packet_url
        };
    }

    static formatCityName(citySlug: string): string {
        const cityMap: Record<string, string> = {
            'cityofpaloalto': 'Palo Alto',
            'palo-alto': 'Palo Alto',
            'mountain-view': 'Mountain View',
            'san-francisco': 'San Francisco'
        };
        
        return cityMap[citySlug] || citySlug.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    private static generateSummary(title: string): string {
        // Generate a basic summary based on title keywords
        const lowerTitle = title.toLowerCase();
        
        if (lowerTitle.includes('council')) {
            return 'City council proceedings and municipal decisions';
        } else if (lowerTitle.includes('planning')) {
            return 'Planning and development discussions';
        } else if (lowerTitle.includes('budget')) {
            return 'Budget discussions and financial matters';
        } else {
            return 'Municipal meeting agenda and discussions';
        }
    }
}
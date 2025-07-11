# Engagic - Civic Engagement Made Simple

Engagic is an AI-powered civic engagement platform that makes local government meetings accessible by automatically discovering, processing, and summarizing city council agendas.

## Features

- **Meeting Discovery**: Automatically finds and indexes city council meetings from multiple platforms (PrimeGov, CivicClerk, Legistar, etc.)
- **AI Summaries**: Uses Claude to generate human-readable summaries of lengthy PDF agendas
- **Smart Search**: Search by zipcode or city name with intelligent disambiguation
- **Cache-First Design**: Instant responses with pre-processed meeting data
- **Privacy-First**: No user tracking, no accounts required, just public civic data

## Architecture

The system consists of three main components:

1. **API Server** (`app/app.py`) - FastAPI backend serving cached meeting data
2. **Background Daemon** (`app/daemon.py`) - Continuously syncs and processes meeting data
3. **Frontend** (`frontend/`) - SvelteKit web interface

## Setup Instructions

### Prerequisites

- Python 3.8+
- Node.js 18+
- Anthropic API key for AI summaries

### Backend Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/engagic.git
cd engagic
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install Python dependencies:
```bash
cd app
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
# Required
export ANTHROPIC_API_KEY="your-api-key-here"
export ENGAGIC_ADMIN_TOKEN="your-secure-admin-token"

# Optional (defaults shown)
export ENGAGIC_DB_DIR="./data"
export ENGAGIC_HOST="0.0.0.0"
export ENGAGIC_PORT="8000"
export ENGAGIC_LOG_LEVEL="INFO"
```

5. Initialize the databases:
```bash
python app.py --init-db
```

6. Start the API server:
```bash
python app.py
```

7. In a separate terminal, start the background daemon:
```bash
python daemon.py
```

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm run dev
```

The application will be available at `http://localhost:5173`

## Usage

1. **Search for meetings**: Enter a zipcode (e.g., "94301") or city name (e.g., "Palo Alto, CA")
2. **Browse meetings**: Click on a city to see upcoming meetings
3. **View summaries**: Click on a meeting to see its AI-generated summary

## API Endpoints

- `POST /api/search` - Search for meetings by zipcode or city name
- `POST /api/process-agenda` - Get cached meeting summary
- `GET /api/health` - System health check
- `GET /api/stats` - Cache statistics

### Admin Endpoints (requires Bearer token)

- `GET /api/admin/city-requests` - View requested cities
- `POST /api/admin/sync-city/{city_slug}` - Force sync a city
- `POST /api/admin/process-meeting` - Force process a meeting

## Development

### Running Tests
```bash
cd app
python -m pytest tests/
```

### Adding New City Adapters

To support a new city platform, add an adapter class in `app/adapters.py`:

```python
class NewPlatformAdapter:
    def __init__(self, city_slug: str):
        self.city_slug = city_slug
    
    def upcoming_packets(self):
        # Implement meeting discovery logic
        pass
```

## Configuration

Key configuration options via environment variables:

- `ENGAGIC_RATE_LIMIT_REQUESTS`: API rate limit (default: 30 requests/minute)
- `ENGAGIC_SYNC_INTERVAL_HOURS`: City sync frequency (default: 72 hours)
- `ENGAGIC_PROCESSING_INTERVAL_HOURS`: AI processing frequency (default: 2 hours)
- `ENGAGIC_DEBUG`: Enable debug mode (default: false)

## Security Considerations

- Admin endpoints require bearer token authentication
- All user inputs are validated and sanitized
- Rate limiting prevents abuse
- No personal data is collected or stored

## License

This project is open source. See LICENSE file for details.

## Contributing

Contributions are welcome! Reach out through appropriate channels

## Acknowledgments

Built with FastAPI, SvelteKit, SQLite, and Anthropic's Claude AI.
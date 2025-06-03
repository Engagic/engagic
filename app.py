from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from adapters import PrimeGovAdapter
from fullstack import AgendaProcessor

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://engagic.org"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/meetings")
async def get_meetings(city: str = "cityofpaloalto"):
    adapter = PrimeGovAdapter(city)
    return list(adapter.upcoming_packets())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

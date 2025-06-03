import json
from adapters import PrimeGovAdapter

async def on_request(context):
    request = context.request
    
    # Get city from query params
    url = request.url
    city = url.searchparams.get('city', 'cityofpaloalto')
    
    try:
        adapter = PrimeGovAdapter(city)
        meetings = list(adapter.upcoming_packets())
        
        return Response(
            json.dumps(meetings),
            headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            headers={"Content-Type": "application/json"}
        )

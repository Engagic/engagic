import json
import os
from fullstack import AgendaProcessor

async def on_request(context):
    request = context.request
    
    if request.method != "POST":
        return Response("Method not allowed", status=405)
    
    try:
        data = await request.json()
        agenda_url = data.get('url')
        
        if not agenda_url:
            return Response(
                json.dumps({"error": "URL required"}),
                status=400,
                headers={"Content-Type": "application/json"}
            )
        
        # Get API key from environment
        api_key = context.env.ANTHROPIC_API_KEY
        processor = AgendaProcessor(api_key)
        
        # Process the agenda
        summary = processor.process_agenda(agenda_url, save_raw=False, save_cleaned=False)
        
        return Response(
            json.dumps({"summary": summary}),
            headers={"Content-Type": "application/json"}
        )
    
    except Exception as e:
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            headers={"Content-Type": "application/json"}
        )

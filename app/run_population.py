from sqlalchemy import func
from uszipcode import SearchEngine, SimpleZipcode
from database import MeetingDatabase
import requests

search_session = requests.Session()

vendor_names = ["granicus", "primegov", "legistar", "civicclerk", "novusagenda", "civicplus", "municode"]

with SearchEngine() as search:
    session = search.ses
    if session is not None:
        results = (
            session.query(
                SimpleZipcode.major_city,
                SimpleZipcode.state,
                func.sum(SimpleZipcode.population).label("population"),
            )
            .group_by(SimpleZipcode.major_city, SimpleZipcode.state)
            .order_by(func.sum(SimpleZipcode.population).desc())
            .all()
        )

    for city, state, pop in results:
        for vendor in vendor_names:
            response = search_session.get(f"https://www.google.com/search?q={city},{state} {vendor}")
            print(response.text)

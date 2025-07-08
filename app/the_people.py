from sqlalchemy import func
from uszipcode import SearchEngine, SimpleZipcode

with SearchEngine() as search:
    session = search.ses

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
        print(f"{city}, {state}: {pop}")

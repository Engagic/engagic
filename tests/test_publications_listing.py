from datetime import date

from vendors.adapters.custom.publications_adapter_async import AsyncPublicationsAdapter

BASE = "https://example.gov/regulations"


def collect(html):
    adapter = AsyncPublicationsAdapter("example", site={"index": [BASE]})
    found = {}
    adapter._collect(adapter._root(f"<html><body><main>{html}</main></body></html>"), BASE, found)
    return found


def test_marked_translations_drop_even_when_the_title_says_english():
    # NYC DOE D-170: every translation's title names "English Language Learners".
    title = "D-170 Selection of Members of the Citywide Council on English Language Learners"
    found = collect(f"""
      <table>
        <tr><td><a href="/docs/d-170-english.pdf">{title} -- English</a></td><td>English</td></tr>
        <tr><td><a href="/docs/d-170-arabic.pdf">{title} -- Arabic</a></td><td>Arabic</td></tr>
        <tr><td><a href="/docs/d-170-ht.pdf">{title} -- French (Haiti)</a></td><td>Haitian Creole</td></tr>
        <tr><td><a href="/docs/d-170-zh.pdf">中文 - 繁體</a></td><td>Chinese Traditional</td><td>Document</td></tr>
      </table>""")
    assert list(found) == ["https://example.gov/docs/d-170-english.pdf"]
    assert found["https://example.gov/docs/d-170-english.pdf"].title == title


def test_translations_marked_only_in_the_file_name_drop_beside_their_original():
    found = collect("""
      <ul>
        <li><a href="/docs/a-450-final.pdf">A-450 Safety Transfers</a></li>
        <li><a href="/docs/a-450-final-uzbek.pdf">A-450 Safety Transfers</a></li>
      </ul>""")
    assert list(found) == ["https://example.gov/docs/a-450-final.pdf"]


def test_a_report_about_a_language_is_not_a_translation():
    found = collect("""
      <ul>
        <li><a href="/r/spanish-services.pdf">Language Access: Spanish</a></li>
        <li><a href="/r/jails.pdf">County Jails</a></li>
      </ul>""")
    assert len(found) == 2


def test_dates_come_only_from_what_the_listing_states_about_one_document():
    found = collect("""
      <p>Page updated June 5, 2025</p>
      <div>
        <a href="/r/alpr.pdf">Our Flock of ALPR Cameras</a>
        <a href="/r/food.pdf">More Food for Thought</a>
        <a href="/r/youth.pdf">Vacant, Valuable, and Vulnerable</a>
      </div>
      <table><tr><td>March 3, 2026</td><td><a href="/r/compost.pdf">Compost Compliance</a></td></tr></table>
      <a href="/r/c-602-9-2-2000-final.pdf">C-602 Attendance</a>""")
    dates = {url.rsplit("/", 1)[-1]: p.published_on for url, p in found.items()}
    assert dates["alpr.pdf"] is None and dates["food.pdf"] is None
    assert dates["compost.pdf"] == date(2026, 3, 3)
    assert dates["c-602-9-2-2000-final.pdf"] == date(2000, 9, 2)


def test_generic_link_text_takes_the_row_title():
    found = collect('<ul><li>Measuring Measure K Transparency <a href="/r/k.pdf">PDF</a></li></ul>')
    assert found["https://example.gov/r/k.pdf"].title == "Measuring Measure K Transparency"


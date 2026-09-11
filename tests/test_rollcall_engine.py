"""Generic minutes engine, on snippets lifted from the 2026-09-11 reservoir."""

from parsing.rollcall.attendance import parse_attendance
from parsing.rollcall.align import anchor_items
from parsing.rollcall.engine import Gazetteer, parse_meeting
from parsing.rollcall.evidence import find_evidence


ALBUQUERQUE = """
      Attendance:
                        Present  5 -  Dan Lewis, Joaquín Baca, Dan Champine, Klarissa Peña, and Stephanie
                               W. Telles
a.    EC-26-176        Establishing Residential Parking Permits - 400 Hannett Avenue
                    A motion was made by Councilor Lewis that this matter be Sent to Council with
                          a recommendation of Be Approved. The motion carried by the following vote:
                              For:  5 -  Lewis, Baca, Champine, Peña, and Telles
b.    EC-26-202         Notification of a grant application submitted by the Aviation
                    A motion was made by Councilor Lewis that this matter be Overridden. The motion failed by the following vote:
                              For:  2 -  Lewis, Baca
                         Against:  3 -  Champine, Peña, and Telles
"""

ALAMEDA = """
   Action
    Supervisor Tam motioned, and Supervisor Miley seconded, to recommend approval of the Draft
    Ordinance Prohibiting the Sale of Nitrous Oxide and Nitrous Oxide Devices.
    Ayes: Supervisor Tam, Supervisor Miley – Two (2)
    Noes:
   Excused:
    Abstained:
   Motion passed 2/0
"""

ALPHARETTA = """
         1.  DRB Meeting Minutes of June 19, 2026
     Board Member Rowen offered a motion to approve.
                Board Member Owens seconded the motion.
                Motion carried (6-0).
"""


class TestAttendance:
    def test_label_with_count_wrapping_lines(self):
        att = parse_attendance(ALBUQUERQUE)
        assert att.present == ["Dan Lewis", "Joaquín Baca", "Dan Champine", "Klarissa Peña", "Stephanie W. Telles"]
        assert att.present_count == 5

    def test_narrative_sentence_across_lines(self):
        text = (
            "Mayor Moriwaki, Deputy Mayor Hytopoulos and Councilmembers Lant, Mathews,\n"
            "Nelson, and Schneider were present. Councilmember Fantroy-Johnson was absent\nand excused."
        )
        att = parse_attendance(text)
        assert att.present == ["Moriwaki", "Hytopoulos", "Councilmembers Lant", "Mathews", "Nelson", "Schneider"]
        assert att.absent == ["Fantroy-Johnson"]


class TestEvidence:
    def test_for_against_lists_with_counts(self):
        block = ALBUQUERQUE.split("b.    EC-26-202")[1]
        ev = find_evidence(block)
        assert len(ev) == 1
        assert ev[0].outcome == "FAIL"
        assert [(s.value, s.names, s.stated) for s in ev[0].sections] == [
            ("AYE", ["Lewis", "Baca"], 2),
            ("NO", ["Champine", "Peña", "Telles"], 3),
        ]

    def test_lists_before_result_with_spelled_count(self):
        ev = find_evidence(ALAMEDA)
        assert ev[-1].outcome == "PASS"
        assert ev[-1].tally == (2, 0, 0)
        assert [(s.value, s.names) for s in ev[-1].sections if s.names] == [("AYE", ["Tam", "Miley"])]

    def test_tally_only(self):
        ev = find_evidence(ALPHARETTA)
        assert ev[-1].outcome == "PASS" and ev[-1].tally == (6, 0, 0) and not ev[-1].named


class TestGazetteer:
    def test_accents_and_middle_initials_do_not_split_a_member(self):
        gz = Gazetteer(["Klarissa J. Peña", "Klarissa Pena", "Joaquin Baca", "Joaquín Baca"])
        assert gz.resolve("Peña") == "Klarissa J. Peña"
        assert gz.resolve("Councilor Baca") == "Joaquin Baca"

    def test_shared_surname_is_ambiguous(self):
        gz = Gazetteer(["Dan Lewis", "Shontel Lewis"])
        assert gz.resolve("Lewis") is None
        assert gz.resolve("Dan Lewis") == "Dan Lewis"


class TestEngine:
    ITEMS = [
        {"id": "i1", "sequence": 2, "agenda_number": "a.", "matter_file": "EC-26-176", "matter_id": "m1", "title": "Establishing Residential Parking Permits"},
        {"id": "i2", "sequence": 3, "agenda_number": "b.", "matter_file": "EC-26-202", "matter_id": "m2", "title": "Notification of a grant application"},
    ]

    def test_named_votes_from_attendance_roster_only(self):
        parsed = parse_meeting(ALBUQUERQUE, self.ITEMS, roster=[])
        assert parsed.items_anchored == 2
        assert [p.method for p in parsed.published] == ["named", "named"]
        first, second = parsed.published
        assert first.outcome == "PASS" and len(first.member_votes) == 5
        assert second.outcome == "FAIL"
        assert dict(second.member_votes)["Klarissa Peña"] == "NO"
        assert second.tally["yes"] == 2 and second.tally["no"] == 3

    def test_unanimous_tally_attributes_against_attendance(self):
        text = "Present: Smith, Jones, Lee\n" + ALPHARETTA.replace("(6-0)", "(3-0)")
        items = [{"id": "i1", "sequence": 1, "agenda_number": "1.", "matter_file": None, "matter_id": "m1", "title": "DRB Meeting Minutes of June 19, 2026"}]
        parsed = parse_meeting(text, items, roster=[])
        assert parsed.published and parsed.published[0].method == "unanimous"
        assert sorted(parsed.published[0].member_votes) == [("Jones", "AYE"), ("Lee", "AYE"), ("Smith", "AYE")]

    def test_split_tally_without_names_is_outcome_only(self):
        text = "Present: Smith, Jones, Lee, Kim\n" + ALPHARETTA.replace("(6-0)", "(3-1)")
        items = [{"id": "i1", "sequence": 1, "agenda_number": "1.", "matter_file": None, "matter_id": "m1", "title": "DRB Meeting Minutes of June 19, 2026"}]
        parsed = parse_meeting(text, items, roster=[])
        assert parsed.published[0].method == "tally" and parsed.published[0].member_votes == []

    def test_unresolvable_name_abstains(self):
        head, tail = ALBUQUERQUE.split("a.    EC-26-176")
        text = head + "a.    EC-26-176" + tail.replace("Telles", "Nobody")
        parsed = parse_meeting(text, self.ITEMS, roster=[])
        assert parsed.published == []
        assert any("unresolved" in r for ab in parsed.abstained for r in ab.reasons)


class TestAlign:
    def test_measurement_numbers_are_not_agenda_anchors(self):
        text = "43.7 %, where 30% is the maximum\nVote: 3-0-0"
        items = [{"id": "x", "sequence": 1, "agenda_number": "43.7", "matter_file": None, "matter_id": "m", "title": "%, where 30% is the maximum amount"}]
        assert anchor_items(text, items) == [] or anchor_items(text, items)[0].rung != "agenda_number"

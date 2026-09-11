"""Generic minutes engine: items in, attributed votes out, or nothing.

    attendance = parse_attendance(text)
    blocks     = align(text, items)
    for block:  evidence = find_evidence(block)
                publish the last evidence per item through the gate

Attribution tiers, in order of what the document supports:
  named      the clerk listed names per category; every name must resolve
             uniquely against roster + attendance, each member at most once,
             list sizes must equal stated counts and the tally when printed
  unanimous  a tally with zero dissent whose yes-count equals the attendance
             present-count: everyone present voted aye, the absent are absent
  tally      outcome and counts only; no per-member rows

Anything the arithmetic cannot confirm is abstained with a reason, never
guessed. Confidence 7/10 overall; the named tier is the spike's gate.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from parsing.rollcall.align import anchor_items, blocks
from parsing.rollcall.attendance import Attendance, parse_attendance
from parsing.rollcall.evidence import Evidence, find_evidence
from parsing.rollcall.names import clean_name, fold


class Gazetteer:
    """Raw minutes name -> canonical roster name; ambiguous keys resolve to nothing."""

    def __init__(self, roster: Sequence[str]):
        keys: Dict[str, set] = {}
        # One canonical spelling per folded name, so accented and plain
        # variants of the same member do not make their surname ambiguous.
        by_fold: Dict[str, str] = {}
        for r in roster:
            cleaned = clean_name(r)
            if not cleaned:
                continue
            parts = fold(cleaned).split()
            # "Klarissa J. Peña" and "Klarissa Peña" are one person: key on
            # first and last token so a middle initial cannot split them.
            identity = parts[0] + " " + parts[-1] if len(parts) >= 2 else parts[0]
            by_fold.setdefault(identity, cleaned)
        self.canonical = sorted(by_fold.values())
        for full in self.canonical:
            parts = fold(full).split()
            variants = {fold(full), parts[-1]}
            if len(parts) >= 2:
                variants.add(" ".join(parts[-2:]))
                variants.add(parts[0][0] + ". " + parts[-1])
            for v in variants:
                keys.setdefault(v, set()).add(full)
        self.keys = {k: next(iter(v)) for k, v in keys.items() if len(v) == 1}

    def resolve(self, raw: str) -> Optional[str]:
        k = fold(clean_name(raw))
        if not k:
            return None
        if k in self.keys:
            return self.keys[k]
        parts = k.split()
        if len(parts) >= 2 and " ".join(parts[-2:]) in self.keys:
            return self.keys[" ".join(parts[-2:])]
        if parts and parts[-1] in self.keys:
            return self.keys[parts[-1]]
        return None


@dataclass
class ItemVotes:
    item: Any
    method: str                                  # named | unanimous | tally
    outcome: Optional[str]                       # PASS | FAIL | None
    tally: Dict[str, int]
    member_votes: List[Tuple[str, str]] = field(default_factory=list)
    motion_text: str = ""
    offset: int = 0
    rung: str = ""


@dataclass
class Abstention:
    item: Any
    reasons: List[str]
    motion_text: str


@dataclass
class MeetingParse:
    attendance: Attendance
    published: List[ItemVotes] = field(default_factory=list)
    abstained: List[Abstention] = field(default_factory=list)
    items_anchored: int = 0
    items_total: int = 0
    evidence_seen: int = 0


def _tally_from_sections(ev: Evidence) -> Dict[str, int]:
    tally = {"yes": 0, "no": 0, "abstain": 0, "absent": 0, "present": 0}
    for s in ev.sections:
        n = len(s.names) if s.names else (s.stated or 0)
        key = {"AYE": "yes", "NO": "no", "ABSTAIN": "abstain", "RECUSED": "abstain",
               "ABSENT": "absent", "EXCUSED": "absent", "PRESENT": "present", "NONVOTING": "present"}[s.value]
        tally[key] += n
    return tally


def _gate_named(ev: Evidence, gazetteer: Gazetteer) -> Tuple[List[Tuple[str, str]], List[str]]:
    reasons: List[str] = []
    votes: List[Tuple[str, str]] = []
    seen: Dict[str, str] = {}
    for section in ev.sections:
        if section.stated is not None and section.names and len(section.names) != section.stated:
            reasons.append(f"tally: {section.value} extracted {len(section.names)} names, stated {section.stated}")
        for raw in section.names:
            full = gazetteer.resolve(raw)
            if full is None:
                reasons.append(f"unresolved: {raw}")
                continue
            if full in seen:
                reasons.append(f"duplicate: {full} in {seen[full]} and {section.value}")
                continue
            seen[full] = section.value
            votes.append((full, section.value))
    if ev.tally:
        yes = sum(1 for _, v in votes if v == "AYE")
        no = sum(1 for _, v in votes if v == "NO")
        if (yes, no) != (ev.tally[0], ev.tally[1]):
            reasons.append(f"tally: lists {yes}-{no} vs printed {ev.tally[0]}-{ev.tally[1]}")
    if not votes:
        reasons.append("empty: no member votes extracted")
    return votes, reasons


def parse_meeting(text: str, items: Sequence[Dict[str, Any]], roster: Sequence[str]) -> MeetingParse:
    attendance = parse_attendance(text)
    result = MeetingParse(attendance=attendance, items_total=len(items))
    gazetteer = Gazetteer(list(roster) + attendance.present + attendance.absent)
    present = [gazetteer.resolve(n) or clean_name(n) for n in attendance.present]
    absent = [gazetteer.resolve(n) or clean_name(n) for n in attendance.absent]

    anchors = anchor_items(text, items)
    result.items_anchored = len(anchors)
    for block in blocks(text, anchors):
        evidence = find_evidence(text[block["start"]:block["end"]])
        if not evidence:
            continue
        result.evidence_seen += len(evidence)
        ev = evidence[-1]
        motion_text = ev.result_text
        offset = block["start"] + ev.offset

        if ev.named:
            votes, reasons = _gate_named(ev, gazetteer)
            if reasons:
                result.abstained.append(Abstention(item=block["item"], reasons=reasons, motion_text=motion_text))
                continue
            tally = _tally_from_sections(ev)
            outcome = ev.outcome or ("PASS" if tally["yes"] > tally["no"] else "FAIL")
            result.published.append(ItemVotes(
                item=block["item"], method="named", outcome=outcome, tally=tally,
                member_votes=votes, motion_text=motion_text, offset=offset, rung=block["rung"],
            ))
            continue

        if ev.tally:
            yes, no, third = ev.tally
            tally = {"yes": yes, "no": no, "abstain": third, "absent": len(absent), "present": 0}
            outcome = ev.outcome or ("PASS" if yes > no else "FAIL")
            if no == 0 and third == 0 and present and len(present) == yes:
                member_votes = [(n, "AYE") for n in present] + [(n, "ABSENT") for n in absent]
                result.published.append(ItemVotes(
                    item=block["item"], method="unanimous", outcome=outcome, tally=tally,
                    member_votes=member_votes, motion_text=motion_text, offset=offset, rung=block["rung"],
                ))
            else:
                result.published.append(ItemVotes(
                    item=block["item"], method="tally", outcome=outcome, tally=tally,
                    motion_text=motion_text, offset=offset, rung=block["rung"],
                ))
            continue

        if ev.unanimous and ev.outcome and present:
            tally = {"yes": len(present), "no": 0, "abstain": 0, "absent": len(absent), "present": 0}
            result.published.append(ItemVotes(
                item=block["item"], method="unanimous", outcome=ev.outcome, tally=tally,
                member_votes=[(n, "AYE") for n in present] + [(n, "ABSENT") for n in absent],
                motion_text=motion_text, offset=offset, rung=block["rung"],
            ))
            continue

        if ev.outcome:
            result.published.append(ItemVotes(
                item=block["item"], method="outcome", outcome=ev.outcome,
                tally={}, motion_text=motion_text, offset=offset, rung=block["rung"],
            ))
            continue
        result.abstained.append(Abstention(item=block["item"], reasons=["no outcome or tally"], motion_text=motion_text))
    return result

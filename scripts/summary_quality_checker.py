#!/usr/bin/env python3
"""
Summary Quality Checker for Engagic Meeting Summaries

Analyzes and validates AI-generated meeting summaries to identify:
- API errors
- Processing failures
- Low-quality content
- Truncated/incomplete summaries
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import re
import argparse
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

from config import get_logger

try:
    from config import Config

    config = Config()
    MEETINGS_DB_PATH = config.UNIFIED_DB_PATH
except ImportError:
    # Fallback if config not available
    MEETINGS_DB_PATH = "/root/engagic/data/engagic.db"

logger = get_logger(__name__).bind(component="quality_checker")


class SummaryQuality(Enum):
    GOOD = "good"
    ERROR = "error"
    TRUNCATED = "truncated"
    TOO_SHORT = "too_short"
    PROCESSING_FAILURE = "processing_failure"
    EMPTY = "empty"
    SUSPICIOUS = "suspicious"


@dataclass
class QualityResult:
    quality: SummaryQuality
    confidence: float  # 1-10 scale
    issues: List[str]
    fixable: bool


class SummaryQualityChecker:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or MEETINGS_DB_PATH
        self.error_patterns = [
            (r"Unable to process this PDF", SummaryQuality.PROCESSING_FAILURE),
            (r"[Ee]rror", SummaryQuality.ERROR),
            (r"API rate limit", SummaryQuality.ERROR),
            (r"Request failed", SummaryQuality.ERROR),
            (r"file may be corrupted", SummaryQuality.PROCESSING_FAILURE),
            (r"password-protected", SummaryQuality.PROCESSING_FAILURE),
            (r"unsupported format", SummaryQuality.PROCESSING_FAILURE),
            (r"Connection timeout", SummaryQuality.ERROR),
            (r"Internal server error", SummaryQuality.ERROR),
        ]

        self.quality_thresholds = {
            "min_length": 100,
            "max_length": 50000,
            "min_sections": 2,
            "truncation_indicators": ["...", "truncated", "cut off", "[...]"],
        }

    def check_summary(self, summary: Optional[str]) -> QualityResult:
        """Analyze a single summary for quality issues"""
        if not summary:
            return QualityResult(
                quality=SummaryQuality.EMPTY,
                confidence=10.0,
                issues=["Summary is empty or NULL"],
                fixable=True,
            )

        issues = []

        # Check for error patterns
        for pattern, quality_type in self.error_patterns:
            if re.search(pattern, summary, re.IGNORECASE):
                issues.append(f"Contains error pattern: {pattern}")
                return QualityResult(
                    quality=quality_type,
                    confidence=9.0,
                    issues=issues,
                    fixable=quality_type == SummaryQuality.ERROR,
                )

        # Check length
        if len(summary) < self.quality_thresholds["min_length"]:
            issues.append(
                f"Too short ({len(summary)} chars < {self.quality_thresholds['min_length']})"
            )
            return QualityResult(
                quality=SummaryQuality.TOO_SHORT,
                confidence=8.0,
                issues=issues,
                fixable=True,
            )

        # Check for truncation
        for indicator in self.quality_thresholds["truncation_indicators"]:
            if summary.endswith(indicator) or summary.count(indicator) > 2:
                issues.append(f"Appears truncated (contains '{indicator}')")
                return QualityResult(
                    quality=SummaryQuality.TRUNCATED,
                    confidence=7.0,
                    issues=issues,
                    fixable=True,
                )

        # Check for structure (should have sections)
        has_sections = any(
            [
                "**" in summary,
                "##" in summary,
                "Key Agenda Items:" in summary,
                "Important Details:" in summary,
                "Public Participation:" in summary,
            ]
        )

        if not has_sections:
            issues.append("Missing structured sections")
            confidence = 5.0
        else:
            confidence = 9.0

        # Check for suspicious patterns
        suspicious_patterns = [
            (r"^=== DOCUMENT \d+ ===$", "Incomplete processing marker"),
            (r"^\d+\|", "Raw database output"),
            (r"^CREATE TABLE", "SQL schema in summary"),
        ]

        for pattern, description in suspicious_patterns:
            if re.search(pattern, summary, re.MULTILINE):
                issues.append(description)
                return QualityResult(
                    quality=SummaryQuality.SUSPICIOUS,
                    confidence=6.0,
                    issues=issues,
                    fixable=True,
                )

        if issues:
            return QualityResult(
                quality=SummaryQuality.SUSPICIOUS,
                confidence=confidence,
                issues=issues,
                fixable=True,
            )

        return QualityResult(
            quality=SummaryQuality.GOOD, confidence=confidence, issues=[], fixable=False
        )

    def analyze_database(self) -> Dict[str, any]:
        """Analyze all summaries in the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all summaries
        cursor.execute("""
            SELECT id, banana, title, summary
            FROM meetings
            WHERE summary IS NOT NULL
        """)

        results = {
            "total": 0,
            "by_quality": {},
            "fixable": [],
            "unfixable": [],
            "cities_affected": set(),
            "detailed_issues": [],
        }

        for row in cursor.fetchall():
            meeting_id, city, name, summary = row
            quality_result = self.check_summary(summary)

            results["total"] += 1

            # Track by quality type
            quality_key = quality_result.quality.value
            if quality_key not in results["by_quality"]:
                results["by_quality"][quality_key] = 0
            results["by_quality"][quality_key] += 1

            # Track fixable vs unfixable
            if quality_result.quality != SummaryQuality.GOOD:
                results["cities_affected"].add(city)
                issue_detail = {
                    "id": meeting_id,
                    "city": city,
                    "meeting": name,
                    "quality": quality_key,
                    "confidence": quality_result.confidence,
                    "issues": quality_result.issues,
                }

                if quality_result.fixable:
                    results["fixable"].append(issue_detail)
                else:
                    results["unfixable"].append(issue_detail)

                # Keep first 10 detailed issues for review
                if len(results["detailed_issues"]) < 10:
                    issue_detail["summary_preview"] = summary[:200] if summary else ""
                    results["detailed_issues"].append(issue_detail)

        conn.close()

        # Convert set to list for JSON serialization
        results["cities_affected"] = list(results["cities_affected"])

        return results

    def get_fixable_meetings(self) -> List[Tuple[int, str, str]]:
        """Get list of meetings that can be reprocessed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, banana, title, summary
            FROM meetings
            WHERE summary IS NOT NULL
        """)

        fixable = []
        for row in cursor.fetchall():
            meeting_id, banana, title, summary = row
            result = self.check_summary(summary)
            if result.fixable and result.quality != SummaryQuality.GOOD:
                fixable.append((meeting_id, banana, title))

        conn.close()
        return fixable

    def clear_bad_summaries(
        self, quality_types: List[SummaryQuality], dry_run: bool = True
    ) -> int:
        """Clear summaries of specified quality types from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # First identify what would be cleared
        cursor.execute("""
            SELECT id, banana, title, summary
            FROM meetings
            WHERE summary IS NOT NULL
        """)

        to_clear = []
        for row in cursor.fetchall():
            meeting_id, city, name, summary = row
            result = self.check_summary(summary)
            if result.quality in quality_types:
                to_clear.append((meeting_id, city, name, result.quality.value))

        if dry_run:
            logger.info("dry_run_clear", count=len(to_clear))
            for meeting_id, city, name, quality in to_clear[:5]:
                logger.info("would_clear", city=city, meeting=name, quality=quality)
            if len(to_clear) > 5:
                logger.info("additional_to_clear", remaining=len(to_clear) - 5)
        else:
            # Actually clear the summaries
            meeting_ids = [t[0] for t in to_clear]
            if meeting_ids:
                placeholders = ",".join("?" * len(meeting_ids))
                cursor.execute(
                    f"""
                    UPDATE meetings
                    SET summary = NULL, processing_time = NULL
                    WHERE id IN ({placeholders})
                """,
                    meeting_ids,
                )
                conn.commit()
                logger.info("summaries_cleared", count=len(to_clear))

        conn.close()
        return len(to_clear)

    def get_best_summaries(self, limit: int = 10, min_length: int = 500) -> List[Dict]:
        """Get the highest quality summaries for showcasing"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, banana, title, date, packet_url, summary
            FROM meetings
            WHERE summary IS NOT NULL
            ORDER BY id DESC
        """)

        best_summaries = []

        for row in cursor.fetchall():
            meeting_id, banana, title, date, packet_url, summary = row
            result = self.check_summary(summary)

            # Only include GOOD quality summaries
            if result.quality != SummaryQuality.GOOD:
                continue

            # Additional quality checks for showcasing
            if len(summary) < min_length:
                continue

            # Check for well-structured content
            has_good_structure = all(
                [
                    "**" in summary or "##" in summary,
                    "Key Agenda Items:" in summary or "Important" in summary,
                    summary.count("\n") > 5,  # Multiple paragraphs
                    not summary.startswith("==="),  # No processing markers
                ]
            )

            if not has_good_structure:
                continue

            # Calculate a quality score (1-10)
            quality_score = 10.0

            # Deduct points for issues
            if len(summary) < 1000:
                quality_score -= 2
            if "Public Participation" not in summary:
                quality_score -= 1
            if summary.count("**") < 3:  # Few bold sections
                quality_score -= 1

            # Boost for excellent features
            if len(summary) > 2000:
                quality_score = min(10, quality_score + 1)
            if "fiscal impact" in summary.lower() or "budget" in summary.lower():
                quality_score = min(10, quality_score + 0.5)

            best_summaries.append(
                {
                    "id": meeting_id,
                    "banana": banana,
                    "title": title,
                    "date": date,
                    "packet_url": packet_url,
                    "summary": summary,
                    "summary_length": len(summary),
                    "quality_score": quality_score,
                    "preview": summary[:500].replace("\n", " "),
                }
            )

            if len(best_summaries) >= limit * 3:  # Get extra to sort by score
                break

        conn.close()

        # Sort by quality score and return top N
        best_summaries.sort(key=lambda x: x["quality_score"], reverse=True)
        return best_summaries[:limit]

    def get_random_best_summary(self) -> Optional[Dict]:
        """Get a random high-quality summary for showcasing"""
        import random

        # Get top 20 best summaries
        best = self.get_best_summaries(limit=20)

        if not best:
            return None

        # Return a random one from the best
        return random.choice(best)

    def generate_report(self) -> str:
        """Generate a human-readable quality report"""
        analysis = self.analyze_database()

        report = []
        report.append("=" * 60)
        report.append("SUMMARY QUALITY REPORT")
        report.append("=" * 60)
        report.append(f"\nTotal summaries analyzed: {analysis['total']}")
        report.append(f"Cities affected by issues: {len(analysis['cities_affected'])}")

        report.append("\n--- Quality Breakdown ---")
        for quality, count in sorted(
            analysis["by_quality"].items(), key=lambda x: -x[1]
        ):
            percentage = (
                (count / analysis["total"]) * 100 if analysis["total"] > 0 else 0
            )
            report.append(f"  {quality:20s}: {count:5d} ({percentage:5.1f}%)")

        report.append("\n--- Fixable vs Unfixable ---")
        report.append(f"  Fixable issues: {len(analysis['fixable'])}")
        report.append(f"  Unfixable issues: {len(analysis['unfixable'])}")

        if analysis["detailed_issues"]:
            report.append("\n--- Sample Issues (first 10) ---")
            for issue in analysis["detailed_issues"][:10]:
                report.append(f"\n  City: {issue['city']}")
                report.append(f"  Meeting: {issue['meeting'][:50]}...")
                report.append(
                    f"  Quality: {issue['quality']} (confidence: {issue['confidence']:.1f})"
                )
                report.append(f"  Issues: {', '.join(issue['issues'])}")
                if issue.get("summary_preview"):
                    preview = issue["summary_preview"].replace("\n", " ")[:100]
                    report.append(f"  Preview: {preview}...")

        report.append("\n" + "=" * 60)

        return "\n".join(report)


def parse_quality_types(types_str: str) -> List[SummaryQuality]:
    """Parse comma-separated quality types"""
    if not types_str:
        return []

    valid_types = {q.value: q for q in SummaryQuality}
    result = []

    for t in types_str.split(","):
        t = t.strip().lower()
        if t in valid_types:
            result.append(valid_types[t])
        else:
            logger.warning("unknown_quality_type", type=t)

    return result


def main():
    """Run quality check and generate report"""
    parser = argparse.ArgumentParser(
        description="Analyze and manage quality of meeting summaries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate quality report
  python scripts/summary_quality_checker.py
  
  # Clear all error and processing failure summaries
  python scripts/summary_quality_checker.py --clear --types error,processing_failure
  
  # Clear all bad summaries (dry run to preview)
  python scripts/summary_quality_checker.py --clear --types error,processing_failure,empty,suspicious --dry-run
  
  # Show all available quality types
  python scripts/summary_quality_checker.py --list-types
        """,
    )

    parser.add_argument(
        "--clear", action="store_true", help="Clear bad summaries from database"
    )

    parser.add_argument(
        "--types",
        type=str,
        default="",
        help="Comma-separated list of quality types to clear (e.g., error,processing_failure)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be cleared without actually doing it",
    )

    parser.add_argument(
        "--list-types", action="store_true", help="List all available quality types"
    )

    parser.add_argument("--verbose", action="store_true", help="Show detailed output")

    parser.add_argument(
        "--best", action="store_true", help="Show best quality summaries for showcasing"
    )

    parser.add_argument(
        "--random-best", action="store_true", help="Show a random high-quality summary"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of best summaries to show (default: 10)",
    )

    args = parser.parse_args()

    # Handle list types
    if args.list_types:
        print("Available quality types:")
        for q in SummaryQuality:
            print(f"  - {q.value}")
        return

    checker = SummaryQualityChecker()

    # Handle --best flag
    if args.best:
        best = checker.get_best_summaries(limit=args.limit)
        if not best:
            print("No high-quality summaries found")
            return

        print(f"Top {len(best)} Best Quality Summaries")
        print("=" * 60)

        for i, summary_info in enumerate(best, 1):
            print(
                f"\n{i}. {summary_info['city_banana']} - {summary_info['meeting_name']}"
            )
            print(f"   Date: {summary_info['meeting_date']}")
            print(f"   Quality Score: {summary_info['quality_score']:.1f}/10")
            print(f"   Length: {summary_info['summary_length']} chars")
            if args.verbose:
                print(f"   Preview: {summary_info['preview'][:200]}...")

        return

    # Handle --random-best flag
    if args.random_best:
        random_summary = checker.get_random_best_summary()
        if not random_summary:
            print("No high-quality summaries found")
            return

        print("Random High-Quality Meeting Summary")
        print("=" * 60)
        print(f"City: {random_summary['banana']}")
        print(f"Meeting: {random_summary['title']}")
        print(f"Date: {random_summary['date']}")
        print(f"Quality Score: {random_summary['quality_score']:.1f}/10")
        print(f"Packet URL: {random_summary['packet_url']}")
        print("\n--- Summary ---\n")
        print(random_summary["summary"])
        return

    # Default action: generate report
    if not args.clear:
        print(checker.generate_report())

        # Show fixable meetings count
        fixable = checker.get_fixable_meetings()
        print(f"\nTotal fixable meetings: {len(fixable)}")

        if args.verbose and fixable:
            print("\nSample fixable meetings (first 10):")
            for meeting_id, city, meeting_ref in fixable[:10]:
                print(f"  - {city}: {meeting_ref}")

    # Clear action
    else:
        if not args.types:
            print("Error: --types required when using --clear")
            print("Common combinations:")
            print("  --types error,processing_failure,empty   # Clear all errors")
            print("  --types suspicious,truncated,too_short   # Clear quality issues")
            print(
                "  --types all                              # Clear everything except good"
            )
            return

        # Special handling for 'all'
        if args.types == "all":
            quality_types = [q for q in SummaryQuality if q != SummaryQuality.GOOD]
            print("Clearing all bad summaries (excluding 'good')")
        else:
            quality_types = parse_quality_types(args.types)
            if not quality_types:
                print(f"Error: No valid quality types found in '{args.types}'")
                print("Use --list-types to see available options")
                return

        print(f"Quality types to clear: {', '.join(q.value for q in quality_types)}")

        # Perform the clear operation
        count = checker.clear_bad_summaries(quality_types, dry_run=args.dry_run)

        if args.dry_run:
            print(f"\nDRY RUN: Would clear {count} summaries")
            print("Run without --dry-run to actually clear them")
        else:
            print(f"\nSuccessfully cleared {count} summaries")
            print("These meetings will be reprocessed by the background daemon")


if __name__ == "__main__":
    main()

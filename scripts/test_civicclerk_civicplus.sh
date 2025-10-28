#!/bin/bash
# Focused test for CivicClerk and CivicPlus adapters
# Tests 8 cities per vendor to validate adapter functionality

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Results tracking
declare -A results
total_cities=0
success_count=0
failure_count=0
meetings_fetched=0

# Test cities
declare -A civicclerk_cities=(
    ["laytonUT"]="Layton, UT"
    ["odessaTX"]="Odessa, TX"
    ["clintontownshipMI"]="Clinton Township, MI"
    ["ranchocordovaCA"]="Rancho Cordova, CA"
    ["newberlinWI"]="New Berlin, WI"
    ["mcallenTX"]="McAllen, TX"
    ["nacogdochesTX"]="Nacogdoches, TX"
    ["puebloCO"]="Pueblo, CO"
)

declare -A civicplus_cities=(
    ["lahabraCA"]="La Habra, CA"
    ["hemetCA"]="Hemet, CA"
    ["lovelandOH"]="Loveland, OH"
    ["jeffersonvilleIN"]="Jeffersonville, IN"
    ["northrichlandhillsTX"]="North Richland Hills, TX"
    ["cedarhillTX"]="Cedar Hill, TX"
    ["beaumontCA"]="Beaumont, CA"
    ["adrianMI"]="Adrian, MI"
)

echo "========================================"
echo "CivicClerk & CivicPlus Adapter Test"
echo "Testing 16 cities across 2 vendors"
echo "========================================"
echo ""

# Function to test a single city
test_city() {
    local vendor=$1
    local city_banana=$2
    local city_display=$3

    total_cities=$((total_cities + 1))

    echo -e "${YELLOW}[${total_cities}/16]${NC} Testing: ${BLUE}$city_display${NC} ($city_banana) [${vendor}]"

    # Run sync with timeout
    local start_time=$(date +%s)
    if timeout 90s ./deploy.sh sync-city "$city_banana" > /tmp/sync_${city_banana}.log 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))

        # Check if meetings were fetched
        meeting_count=$(sqlite3 data/engagic.db "SELECT COUNT(*) FROM meetings WHERE city_banana='$city_banana'" 2>/dev/null || echo "0")

        if [ "$meeting_count" -gt 0 ]; then
            echo -e "  ${GREEN}✓ SUCCESS${NC} - Fetched $meeting_count meetings (${duration}s)"
            results["$city_banana"]="✓ $meeting_count meetings"
            success_count=$((success_count + 1))
            meetings_fetched=$((meetings_fetched + meeting_count))
        else
            echo -e "  ${YELLOW}⚠ NO MEETINGS${NC} - Sync succeeded but 0 meetings (${duration}s)"
            results["$city_banana"]="⚠ 0 meetings"
            success_count=$((success_count + 1))
        fi
    else
        error=$(tail -3 /tmp/sync_${city_banana}.log 2>/dev/null | grep -E "ERROR|Failed" | head -1 || echo "Unknown error")
        echo -e "  ${RED}✗ FAILED${NC} - $error"
        results["$city_banana"]="✗ Failed"
        failure_count=$((failure_count + 1))

        # Show last few log lines for debugging
        echo -e "  ${YELLOW}Last log lines:${NC}"
        tail -5 /tmp/sync_${city_banana}.log 2>/dev/null | sed 's/^/    /' || echo "    (no log available)"
    fi
    echo ""
}

# Test CivicClerk
echo "========================================"
echo "Testing CivicClerk Adapter (8 cities)"
echo "========================================"
echo ""

for city in "${!civicclerk_cities[@]}"; do
    test_city "civicclerk" "$city" "${civicclerk_cities[$city]}"
    sleep 1  # Brief pause
done

# Test CivicPlus
echo "========================================"
echo "Testing CivicPlus Adapter (8 cities)"
echo "========================================"
echo ""

for city in "${!civicplus_cities[@]}"; do
    test_city "civicplus" "$city" "${civicplus_cities[$city]}"
    sleep 1  # Brief pause
done

# Print summary
echo "========================================"
echo "TEST SUMMARY"
echo "========================================"
echo ""
echo "Total cities tested: $total_cities"
echo -e "${GREEN}Successful syncs: $success_count${NC}"
echo -e "${RED}Failed syncs: $failure_count${NC}"
echo -e "${BLUE}Total meetings fetched: $meetings_fetched${NC}"
echo ""

# Success rate
success_rate=$((success_count * 100 / total_cities))
echo "Success rate: ${success_rate}%"
echo ""

# Detailed results
echo "========================================"
echo "DETAILED RESULTS"
echo "========================================"
echo ""

echo "--- CivicClerk Cities ---"
for city in "${!civicclerk_cities[@]}"; do
    echo "  ${civicclerk_cities[$city]}: ${results[$city]}"
done
echo ""

echo "--- CivicPlus Cities ---"
for city in "${!civicplus_cities[@]}"; do
    echo "  ${civicplus_cities[$city]}: ${results[$city]}"
done
echo ""

# Exit code
if [ $failure_count -gt 0 ]; then
    echo -e "${YELLOW}Some tests failed. Review logs above.${NC}"
    exit 1
elif [ $meetings_fetched -eq 0 ]; then
    echo -e "${YELLOW}All syncs succeeded but no meetings fetched. May need investigation.${NC}"
    exit 0
else
    echo -e "${GREEN}All tests passed! Fetched $meetings_fetched total meetings.${NC}"
    exit 0
fi

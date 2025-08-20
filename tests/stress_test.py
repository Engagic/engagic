#!/usr/bin/env python3
"""Stress test for Engagic API"""

import asyncio
import aiohttp
import time
import random
from typing import List, Dict, Any

API_URL = "http://localhost:8000"

# Test queries
TEST_QUERIES = [
    "94301",  # Palo Alto zipcode
    "10001",  # NYC zipcode  
    "90210",  # Beverly Hills
    "Springfield",  # Ambiguous city
    "Palo Alto, CA",  # City, State
    "Chicago, IL",
    "Austin, TX",
    "Seattle, WA",
    "Boston, MA",
    "Miami, FL",
]

async def make_request(session: aiohttp.ClientSession, endpoint: str, method: str = "GET", data: Dict = None) -> Dict[str, Any]:
    """Make a single request"""
    try:
        start = time.time()
        if method == "POST":
            async with session.post(endpoint, json=data) as response:
                result = await response.json()
                return {
                    "success": True,
                    "status": response.status,
                    "time": time.time() - start,
                    "endpoint": endpoint,
                    "data": result
                }
        else:
            async with session.get(endpoint) as response:
                result = await response.json()
                return {
                    "success": True, 
                    "status": response.status,
                    "time": time.time() - start,
                    "endpoint": endpoint,
                    "data": result
                }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "time": time.time() - start,
            "endpoint": endpoint
        }

async def stress_test_search(session: aiohttp.ClientSession, num_requests: int = 50) -> List[Dict]:
    """Stress test search endpoint"""
    tasks = []
    for i in range(num_requests):
        query = random.choice(TEST_QUERIES)
        task = make_request(session, f"{API_URL}/api/search", "POST", {"query": query})
        tasks.append(task)
    return await asyncio.gather(*tasks)

async def stress_test_mixed(session: aiohttp.ClientSession, num_requests: int = 30) -> List[Dict]:
    """Stress test multiple endpoints"""
    tasks = []
    endpoints = [
        (f"{API_URL}/", "GET", None),
        (f"{API_URL}/api/health", "GET", None),
        (f"{API_URL}/api/stats", "GET", None),
    ]
    
    for i in range(num_requests):
        if i % 3 == 0:
            # Search request
            query = random.choice(TEST_QUERIES)
            task = make_request(session, f"{API_URL}/api/search", "POST", {"query": query})
        else:
            # Random GET endpoint
            endpoint, method, data = random.choice(endpoints)
            task = make_request(session, endpoint, method, data)
        tasks.append(task)
    
    return await asyncio.gather(*tasks)

async def run_stress_tests():
    """Run all stress tests"""
    print("🚀 Starting Engagic API Stress Tests")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        # Warmup
        print("\n📊 Warmup request...")
        warmup = await make_request(session, f"{API_URL}/api/health")
        print(f"  Health check: {warmup['status'] if warmup['success'] else 'FAILED'}")
        
        # Test 1: Search endpoint stress
        print("\n📊 Test 1: Search Endpoint Stress (50 concurrent requests)")
        start = time.time()
        search_results = await stress_test_search(session, 50)
        duration = time.time() - start
        
        successful = sum(1 for r in search_results if r['success'])
        avg_time = sum(r['time'] for r in search_results) / len(search_results)
        
        print(f"  Duration: {duration:.2f}s")
        print(f"  Successful: {successful}/{len(search_results)}")
        print(f"  Average response time: {avg_time*1000:.2f}ms")
        print(f"  Requests/sec: {len(search_results)/duration:.2f}")
        
        # Test 2: Mixed endpoints
        print("\n📊 Test 2: Mixed Endpoints (30 concurrent requests)")
        start = time.time()
        mixed_results = await stress_test_mixed(session, 30)
        duration = time.time() - start
        
        successful = sum(1 for r in mixed_results if r['success'])
        avg_time = sum(r['time'] for r in mixed_results) / len(mixed_results)
        
        print(f"  Duration: {duration:.2f}s")
        print(f"  Successful: {successful}/{len(mixed_results)}")
        print(f"  Average response time: {avg_time*1000:.2f}ms")
        print(f"  Requests/sec: {len(mixed_results)/duration:.2f}")
        
        # Test 3: Rapid fire (sequential)
        print("\n📊 Test 3: Rapid Fire (100 sequential requests)")
        start = time.time()
        for i in range(100):
            query = random.choice(TEST_QUERIES)
            await make_request(session, f"{API_URL}/api/search", "POST", {"query": query})
        duration = time.time() - start
        
        print(f"  Duration: {duration:.2f}s")
        print(f"  Requests/sec: {100/duration:.2f}")
        
        # Check if API is still responsive
        print("\n📊 Final health check...")
        final = await make_request(session, f"{API_URL}/api/health")
        print(f"  Health check: {final['status'] if final['success'] else 'FAILED'}")
        
        if final['success']:
            print("\n✅ All stress tests completed successfully!")
        else:
            print("\n❌ API may be unresponsive after stress tests")

if __name__ == "__main__":
    asyncio.run(run_stress_tests())
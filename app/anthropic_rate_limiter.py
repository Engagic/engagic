"""Anthropic-specific rate limit handler with header parsing"""

import time
import logging
from typing import Optional, Dict
from datetime import datetime
import anthropic

logger = logging.getLogger("engagic")


class AnthropicRateLimiter:
    """Handle Anthropic API rate limits with intelligent backoff"""
    
    def __init__(self):
        self.rate_limit_reset_times = {}  # model -> reset_time
        self.rate_limit_remaining = {}    # model -> remaining requests
        self.last_request_time = {}       # model -> timestamp
        self.requests_per_minute = {}     # model -> list of timestamps
        self.max_requests_per_minute = 10  # Very conservative limit
        
    def parse_rate_limit_headers(self, response_headers: Dict[str, str], model: str = "default"):
        """Parse Anthropic rate limit headers
        
        Headers include:
        - anthropic-ratelimit-requests-limit: Total request limit
        - anthropic-ratelimit-requests-remaining: Remaining requests
        - anthropic-ratelimit-requests-reset: Reset time (ISO 8601)
        - anthropic-ratelimit-tokens-limit: Token limit
        - anthropic-ratelimit-tokens-remaining: Remaining tokens
        - anthropic-ratelimit-tokens-reset: Token reset time
        - retry-after: Seconds to wait (on 429/529 errors)
        """
        
        # Parse remaining requests
        remaining = response_headers.get('anthropic-ratelimit-requests-remaining')
        if remaining:
            self.rate_limit_remaining[model] = int(remaining)
            logger.debug(f"Rate limit remaining for {model}: {remaining}")
        
        # Parse reset time
        reset_time = response_headers.get('anthropic-ratelimit-requests-reset')
        if reset_time:
            # Parse ISO 8601 timestamp
            try:
                reset_dt = datetime.fromisoformat(reset_time.replace('Z', '+00:00'))
                self.rate_limit_reset_times[model] = reset_dt
                logger.debug(f"Rate limit resets at {reset_time} for {model}")
            except Exception as e:
                logger.warning(f"Failed to parse reset time {reset_time}: {e}")
        
        # Check retry-after header (most important for 429/529)
        retry_after = response_headers.get('retry-after')
        if retry_after:
            try:
                wait_seconds = int(retry_after)
                logger.info(f"Anthropic requests retry after {wait_seconds}s")
                return wait_seconds
            except:
                pass
                
        return None
    
    def should_wait(self, model: str = "default") -> Optional[float]:
        """Check if we should wait before making a request"""
        
        # Check per-minute rate limit first
        now = time.time()
        if model not in self.requests_per_minute:
            self.requests_per_minute[model] = []
        
        # Clean up old timestamps (older than 1 minute)
        self.requests_per_minute[model] = [
            ts for ts in self.requests_per_minute[model] 
            if now - ts < 60
        ]
        
        # If we've hit our per-minute limit, calculate wait time
        if len(self.requests_per_minute[model]) >= self.max_requests_per_minute:
            oldest_request = min(self.requests_per_minute[model])
            wait_until = oldest_request + 60
            wait_seconds = wait_until - now
            if wait_seconds > 0:
                logger.info(f"Per-minute rate limit for {model}: {len(self.requests_per_minute[model])}/{self.max_requests_per_minute} requests, waiting {wait_seconds:.1f}s")
                return wait_seconds
        
        # Check if we have a reset time from headers
        reset_time = self.rate_limit_reset_times.get(model)
        if reset_time:
            now_dt = datetime.now(reset_time.tzinfo)
            if now_dt < reset_time:
                wait_seconds = (reset_time - now_dt).total_seconds()
                if wait_seconds > 0:
                    remaining = self.rate_limit_remaining.get(model, 0)
                    if remaining <= 5:  # Be VERY conservative - wait when we have 5 or fewer requests
                        logger.info(f"Rate limit nearly exhausted for {model} ({remaining} remaining), waiting {wait_seconds:.1f}s until reset")
                        return wait_seconds
        
        # Check request spacing (be VERY polite to avoid rate limits)
        last_request = self.last_request_time.get(model)
        if last_request:
            elapsed = now - last_request
            if elapsed < 2.0:  # Minimum 2 seconds between requests
                return 2.0 - elapsed
                
        return None
    
    def record_request(self, model: str = "default"):
        """Record that a request was made"""
        now = time.time()
        self.last_request_time[model] = now
        
        # Track for per-minute rate limiting
        if model not in self.requests_per_minute:
            self.requests_per_minute[model] = []
        self.requests_per_minute[model].append(now)
    
    def handle_rate_limit_error(self, error: Exception, model: str = "default") -> float:
        """Extract wait time from rate limit error
        
        Returns wait time in seconds
        """
        error_str = str(error)
        
        # Try to extract from error message
        if hasattr(error, 'response'):
            headers = getattr(error.response, 'headers', {})
            retry_after = self.parse_rate_limit_headers(headers, model)
            if retry_after:
                return retry_after
        
        # Fallback: extract from error message patterns
        import re
        
        # "Please try again in X seconds"
        match = re.search(r'try again in (\d+(?:\.\d+)?) seconds', error_str, re.IGNORECASE)
        if match:
            return float(match.group(1))
            
        # "Please wait X seconds"
        match = re.search(r'wait (\d+(?:\.\d+)?) seconds', error_str, re.IGNORECASE)
        if match:
            return float(match.group(1))
        
        # Default backoff based on error type (be VERY conservative)
        if "429" in error_str:
            return 120  # 2 minutes for rate limit
        elif "529" in error_str:
            return 60  # 1 minute for overload
        else:
            return 30  # 30 seconds default
    
    def wrap_request(self, func, *args, **kwargs):
        """Wrap an Anthropic API request with rate limit handling"""
        model = kwargs.get('model', 'default')
        
        # Check if we should wait
        wait_time = self.should_wait(model)
        if wait_time:
            logger.info(f"Waiting {wait_time:.1f}s before request due to rate limits")
            time.sleep(wait_time)
        
        # Record request time
        self.record_request(model)
        
        try:
            # Make the request
            response = func(*args, **kwargs)
            
            # Parse headers from successful response
            if hasattr(response, '_headers'):
                self.parse_rate_limit_headers(response._headers, model)
                
            return response
            
        except anthropic.RateLimitError as e:
            # Handle rate limit error
            wait_time = self.handle_rate_limit_error(e, model)
            logger.warning(f"Rate limit hit, waiting {wait_time}s as requested by API")
            time.sleep(wait_time)
            
            # Retry once after waiting
            self.record_request(model)
            return func(*args, **kwargs)
            
        except Exception as e:
            # Check if it's a rate limit-like error
            if any(code in str(e) for code in ['429', '529', 'rate', 'limit', 'overload']):
                wait_time = self.handle_rate_limit_error(e, model)
                logger.warning(f"Rate limit-like error, waiting {wait_time}s")
                time.sleep(wait_time)
                
                # Retry once
                self.record_request(model)
                return func(*args, **kwargs)
            else:
                raise
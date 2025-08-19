"""Rate limit handling for API requests"""

import time
import random
import logging
from typing import Optional, Callable, Any, Dict
from functools import wraps

logger = logging.getLogger("engagic")

class RateLimitHandler:
    """Handle rate limits with exponential backoff and jitter"""
    
    def __init__(self, 
                 initial_delay: float = 1.0,
                 max_delay: float = 60.0,
                 max_retries: int = 5,
                 backoff_factor: float = 2.0):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.consecutive_rate_limits = 0
        self.last_rate_limit_time = 0
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter"""
        # Exponential backoff
        delay = min(self.initial_delay * (self.backoff_factor ** attempt), self.max_delay)
        
        # Add jitter (±25%)
        jitter = delay * 0.25 * (2 * random.random() - 1)
        return max(0.1, delay + jitter)
    
    def should_retry(self, error: Exception) -> bool:
        """Check if error is retryable"""
        error_str = str(error).lower()
        
        # Rate limit errors
        if any(x in error_str for x in ["529", "overloaded", "rate limit", "too many requests"]):
            return True
        
        # Temporary errors
        if any(x in error_str for x in ["timeout", "connection", "temporary"]):
            return True
        
        return False
    
    def handle_rate_limit(self):
        """Track consecutive rate limits"""
        current_time = time.time()
        
        # Reset counter if it's been more than 5 minutes since last rate limit
        if current_time - self.last_rate_limit_time > 300:
            self.consecutive_rate_limits = 0
        
        self.consecutive_rate_limits += 1
        self.last_rate_limit_time = current_time
        
        # If we've hit many rate limits, add extra delay
        if self.consecutive_rate_limits > 3:
            extra_delay = min(300, self.consecutive_rate_limits * 10)  # Max 5 minutes
            logger.warning(f"Multiple rate limits detected ({self.consecutive_rate_limits}), adding {extra_delay}s extra delay")
            time.sleep(extra_delay)
            
        # Emergency brake - if too many consecutive rate limits, pause longer
        if self.consecutive_rate_limits > 20:
            pause_time = 600  # 10 minutes
            logger.error(f"SEVERE RATE LIMITING: {self.consecutive_rate_limits} consecutive failures. Pausing {pause_time}s")
            time.sleep(pause_time)
            self.consecutive_rate_limits = 10  # Reset to lower number after pause
    
    def reset_success(self):
        """Reset rate limit counter on successful request"""
        self.consecutive_rate_limits = 0


def with_rate_limit_retry(handler: Optional[RateLimitHandler] = None):
    """Decorator for functions that need rate limit handling"""
    if handler is None:
        handler = RateLimitHandler()
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_error = None
            
            for attempt in range(handler.max_retries):
                try:
                    result = func(*args, **kwargs)
                    handler.reset_success()
                    return result
                
                except Exception as e:
                    last_error = e
                    
                    if not handler.should_retry(e):
                        logger.error(f"Non-retryable error in {func.__name__}: {e}")
                        raise
                    
                    if "529" in str(e) or "overloaded" in str(e).lower():
                        handler.handle_rate_limit()
                    
                    if attempt < handler.max_retries - 1:
                        delay = handler.calculate_delay(attempt)
                        logger.warning(f"Rate limit hit in {func.__name__}, attempt {attempt + 1}/{handler.max_retries}, "
                                     f"retrying in {delay:.1f}s: {e}")
                        time.sleep(delay)
                    else:
                        logger.error(f"Max retries ({handler.max_retries}) exceeded in {func.__name__}")
            
            raise last_error
        
        return wrapper
    
    return decorator


class APIRateLimitManager:
    """Manage rate limits across multiple API endpoints"""
    
    def __init__(self):
        self.handlers: Dict[str, RateLimitHandler] = {}
        self.global_pause_until = 0
    
    def get_handler(self, endpoint: str) -> RateLimitHandler:
        """Get or create handler for endpoint"""
        if endpoint not in self.handlers:
            self.handlers[endpoint] = RateLimitHandler()
        return self.handlers[endpoint]
    
    def pause_all(self, duration: float):
        """Pause all API calls for a duration"""
        self.global_pause_until = time.time() + duration
        logger.warning(f"Pausing all API calls for {duration}s due to rate limits")
    
    def can_proceed(self) -> bool:
        """Check if we can make API calls"""
        if time.time() < self.global_pause_until:
            remaining = self.global_pause_until - time.time()
            logger.info(f"API calls paused for {remaining:.1f}s more")
            return False
        return True
    
    def wait_if_needed(self):
        """Wait if global pause is active"""
        if time.time() < self.global_pause_until:
            remaining = self.global_pause_until - time.time()
            logger.info(f"Waiting {remaining:.1f}s for rate limit pause to end")
            time.sleep(remaining)
// Error logging and monitoring
import { config } from '$lib/api/config';

interface LogLevel {
	DEBUG: 'debug';
	INFO: 'info';
	WARN: 'warn';
	ERROR: 'error';
}

const LOG_LEVELS: LogLevel = {
	DEBUG: 'debug',
	INFO: 'info',
	WARN: 'warn',
	ERROR: 'error'
};

interface LogEntry {
	level: string;
	message: string;
	timestamp: string;
	context?: Record<string, unknown>;
	error?: Error;
}

class Logger {
	private queue: LogEntry[] = [];
	private isProduction = import.meta.env.PROD;
	
	private log(level: string, message: string, context?: Record<string, unknown>, error?: Error) {
		const entry: LogEntry = {
			level,
			message,
			timestamp: new Date().toISOString(),
			context,
			error
		};
		
		// Console output in development
		if (!this.isProduction) {
			const consoleFn = level === 'error' ? console.error : 
							 level === 'warn' ? console.warn : 
							 console.log;
			
			consoleFn(`[${level.toUpperCase()}]`, message, context || '', error || '');
		}
		
		// Queue for batch sending
		this.queue.push(entry);
		
		// Send immediately for errors
		if (level === 'error') {
			this.flush();
		}
	}
	
	debug(message: string, context?: Record<string, unknown>) {
		this.log(LOG_LEVELS.DEBUG, message, context);
	}
	
	info(message: string, context?: Record<string, unknown>) {
		this.log(LOG_LEVELS.INFO, message, context);
	}
	
	warn(message: string, context?: Record<string, unknown>) {
		this.log(LOG_LEVELS.WARN, message, context);
	}
	
	error(message: string, error?: Error, context?: Record<string, unknown>) {
		this.log(LOG_LEVELS.ERROR, message, context, error);
	}
	
	// Send logs to monitoring service
	async flush() {
		if (this.queue.length === 0) return;
		
		const logs = [...this.queue];
		this.queue = [];
		
		// In production, send to monitoring service
		if (this.isProduction) {
			try {
				// TODO: Integrate with actual monitoring service (Sentry, LogRocket, etc.)
				// For now, just store in localStorage for debugging
				const existingLogs = localStorage.getItem('engagic_logs');
				const allLogs = existingLogs ? JSON.parse(existingLogs) : [];
				allLogs.push(...logs);
				
				// Keep only last 100 logs
				if (allLogs.length > 100) {
					allLogs.splice(0, allLogs.length - 100);
				}
				
				localStorage.setItem('engagic_logs', JSON.stringify(allLogs));
			} catch (e) {
				console.error('Failed to store logs:', e);
			}
		}
	}
	
	// Track user actions for analytics - sends to backend in production
	trackEvent(eventName: string, properties?: Record<string, unknown>) {
		this.info(`Event: ${eventName}`, properties);

		if (this.isProduction) {
			fetch(`${config.apiBaseUrl}/api/events`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ event: eventName, properties }),
				keepalive: true
			}).catch(() => {});
		}
	}
	
	// Track API errors
	trackApiError(endpoint: string, status: number, message: string) {
		this.error(`API Error: ${endpoint}`, undefined, {
			endpoint,
			status,
			message
		});
	}
	
	// Track performance metrics
	trackPerformance(metric: string, value: number) {
		this.info(`Performance: ${metric}`, { value });
	}
}

export const logger = new Logger();

// Auto-flush logs periodically
if (typeof window !== 'undefined') {
	setInterval(() => {
		logger.flush();
	}, 30000); // Every 30 seconds
	
	// Flush on page unload
	window.addEventListener('beforeunload', () => {
		logger.flush();
	});
	
	// Global error handler
	window.addEventListener('error', (event) => {
		logger.error('Uncaught error', event.error, {
			message: event.message,
			filename: event.filename,
			lineno: event.lineno,
			colno: event.colno
		});
	});
	
	// Unhandled promise rejection handler
	window.addEventListener('unhandledrejection', (event) => {
		logger.error('Unhandled promise rejection', event.reason as Error, {
			reason: String(event.reason)
		});
	});
}
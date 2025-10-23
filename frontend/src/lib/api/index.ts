// API module exports
export * from './types';
export { config, errorMessages } from './config';

// Export API functions
import { apiClient } from './api-client';
export const searchMeetings = apiClient.searchMeetings.bind(apiClient);
export const getAnalytics = apiClient.getAnalytics.bind(apiClient);
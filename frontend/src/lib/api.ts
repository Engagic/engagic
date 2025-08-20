// Re-export everything from the new modules
export * from './types';

// Export the API functions for existing code
import { apiClient } from './api-client';
export const searchMeetings = apiClient.searchMeetings.bind(apiClient);
export const getCachedSummary = apiClient.getCachedSummary.bind(apiClient);
export const getAnalytics = apiClient.getAnalytics.bind(apiClient);
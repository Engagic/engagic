// API module exports
export * from './types';
export { config, errorMessages } from './config';

// Export API functions
import { apiClient } from './api-client';
export const searchMeetings = apiClient.searchMeetings.bind(apiClient);
export const getAnalytics = apiClient.getAnalytics.bind(apiClient);
export const searchByTopic = apiClient.searchByTopic.bind(apiClient);
export const getMeeting = apiClient.getMeeting.bind(apiClient);
export const generateFlyer = apiClient.generateFlyer.bind(apiClient);
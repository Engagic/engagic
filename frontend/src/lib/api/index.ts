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
export const getMatterTimeline = apiClient.getMatterTimeline.bind(apiClient);
export const getCityMatters = apiClient.getCityMatters.bind(apiClient);
export const getStateMatters = apiClient.getStateMatters.bind(apiClient);
export const searchCityMeetings = apiClient.searchCityMeetings.bind(apiClient);
export const searchCityMatters = apiClient.searchCityMatters.bind(apiClient);
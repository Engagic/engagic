// API module exports
export * from './types';
export * from './deliberation';
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

// Vote endpoints
export const getMatterVotes = apiClient.getMatterVotes.bind(apiClient);
export const getMeetingVotes = apiClient.getMeetingVotes.bind(apiClient);

// Sponsor endpoints
export const getMatterSponsors = apiClient.getMatterSponsors.bind(apiClient);

// Council Member endpoints
export const getCityCouncilMembers = apiClient.getCityCouncilMembers.bind(apiClient);
export const getCouncilMemberVotes = apiClient.getCouncilMemberVotes.bind(apiClient);
export const getMemberCommittees = apiClient.getMemberCommittees.bind(apiClient);

// Committee endpoints
export const getCityCommittees = apiClient.getCityCommittees.bind(apiClient);
export const getCommittee = apiClient.getCommittee.bind(apiClient);
export const getCommitteeMembers = apiClient.getCommitteeMembers.bind(apiClient);
export const getCommitteeVotes = apiClient.getCommitteeVotes.bind(apiClient);

// Rating endpoints
export const getRatingStats = apiClient.getRatingStats.bind(apiClient);
export const submitRating = apiClient.submitRating.bind(apiClient);

// Issue reporting endpoints
export const getIssues = apiClient.getIssues.bind(apiClient);
export const reportIssue = apiClient.reportIssue.bind(apiClient);

// Trending endpoints
export const getTrendingMatters = apiClient.getTrendingMatters.bind(apiClient);

// Engagement endpoints
export const getMatterEngagement = apiClient.getMatterEngagement.bind(apiClient);
export const getMeetingEngagement = apiClient.getMeetingEngagement.bind(apiClient);
export const logView = apiClient.logView.bind(apiClient);
-- Migration 004: Add composite index for matter-meeting joins
-- Date: 2025-11-16
-- Purpose: Optimize matters timeline queries by adding composite index

-- Add composite index to optimize the matter-meeting join pattern
-- This index specifically optimizes the CTE query in /api/city/{banana}/matters
-- Eliminates N+1 query bottleneck by making the LEFT JOIN faster
CREATE INDEX IF NOT EXISTS idx_items_matter_meeting
ON items(matter_id, meeting_id)
WHERE matter_id IS NOT NULL;

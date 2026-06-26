-- Add AI summary controls to schedule-level standups.
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS ai_summary_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE standup_schedules ADD COLUMN IF NOT EXISTS ai_provider TEXT DEFAULT 'openai';

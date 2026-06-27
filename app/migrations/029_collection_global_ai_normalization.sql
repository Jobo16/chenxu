-- Progress collection tasks should only describe collection behavior.
-- AI normalization is controlled by the global AI settings and built-in/global
-- progress normalization prompt.

ALTER TABLE progress_collections
    ALTER COLUMN questions SET DEFAULT '["请按“项目 + 已完成/正在做 + 下一步 + 风险阻塞”的格式提交进度。"]'::jsonb,
    DROP COLUMN IF EXISTS ai_normalize_enabled,
    DROP COLUMN IF EXISTS ai_provider,
    DROP COLUMN IF EXISTS ai_prompt;

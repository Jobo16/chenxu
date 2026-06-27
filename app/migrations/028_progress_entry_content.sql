-- Collapse progress entry content to the single user-confirmed field used by
-- dashboards and publishing.

ALTER TABLE progress_entries
    ADD COLUMN IF NOT EXISTS content TEXT NOT NULL DEFAULT '';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'progress_entries' AND column_name = 'normalized_text'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'progress_entries' AND column_name = 'progress_text'
    ) THEN
        EXECUTE $sql$
            UPDATE progress_entries
            SET content = COALESCE(NULLIF(normalized_text, ''), NULLIF(progress_text, ''), content, '')
            WHERE content = ''
        $sql$;
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'progress_entries' AND column_name = 'normalized_text'
    ) THEN
        EXECUTE $sql$
            UPDATE progress_entries
            SET content = COALESCE(NULLIF(normalized_text, ''), content, '')
            WHERE content = ''
        $sql$;
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'progress_entries' AND column_name = 'progress_text'
    ) THEN
        EXECUTE $sql$
            UPDATE progress_entries
            SET content = COALESCE(NULLIF(progress_text, ''), content, '')
            WHERE content = ''
        $sql$;
    END IF;
END $$;

ALTER TABLE progress_entries
    DROP COLUMN IF EXISTS status,
    DROP COLUMN IF EXISTS progress_text,
    DROP COLUMN IF EXISTS raw_message,
    DROP COLUMN IF EXISTS normalized_text,
    DROP COLUMN IF EXISTS ai_analysis;

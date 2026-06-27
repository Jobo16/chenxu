-- Collection tasks now use a single reminder block instead of multiple
-- sequential questions.

UPDATE progress_collections
SET questions = jsonb_build_array(
    COALESCE(
        (
            SELECT string_agg(value, E'\n' ORDER BY ord)
            FROM jsonb_array_elements_text(questions) WITH ORDINALITY AS items(value, ord)
            WHERE btrim(value) <> ''
        ),
        '请按“项目 + 已完成/正在做 + 下一步 + 风险阻塞”的格式提交进度。'
    )
)
WHERE jsonb_typeof(questions) = 'array'
  AND jsonb_array_length(questions) > 1;

-- Core product model: progress collection, normalized progress records,
-- snapshots, and timed publishing. This supersedes the old standup-shaped
-- product model at the Dashboard/API layer.

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(team_id, name)
);

CREATE TABLE IF NOT EXISTS progress_collections (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '每日进度收集',
    channel_id TEXT,
    schedule_time TEXT NOT NULL DEFAULT '09:30',
    schedule_tz TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    schedule_days TEXT NOT NULL DEFAULT 'mon,tue,wed,thu,fri',
    questions JSONB NOT NULL DEFAULT '["请按“项目 + 已完成/正在做 + 下一步 + 风险阻塞”的格式提交进度。"]',
    participants TEXT[] DEFAULT ARRAY[]::TEXT[],
    reminder_minutes INTEGER DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS progress_collections_team_idx ON progress_collections(team_id, active);

CREATE TABLE IF NOT EXISTS progress_entries (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    collection_id INTEGER REFERENCES progress_collections(id) ON DELETE SET NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    user_id TEXT NOT NULL,
    role TEXT DEFAULT '',
    progress_date DATE NOT NULL DEFAULT CURRENT_DATE,
    content TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'feishu_dm',
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS progress_entries_team_date_idx ON progress_entries(team_id, progress_date);
CREATE INDEX IF NOT EXISTS progress_entries_member_idx ON progress_entries(team_id, user_id, progress_date);
CREATE INDEX IF NOT EXISTS progress_entries_project_idx ON progress_entries(team_id, project_id, progress_date);

CREATE TABLE IF NOT EXISTS progress_entry_snapshots (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    entry_id INTEGER REFERENCES progress_entries(id) ON DELETE CASCADE,
    snapshot_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_by TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS progress_snapshots_entry_idx ON progress_entry_snapshots(entry_id, created_at DESC);

CREATE TABLE IF NOT EXISTS publish_jobs (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '定时发布',
    destination_type TEXT NOT NULL DEFAULT 'feishu_channel',
    destination TEXT NOT NULL DEFAULT '',
    schedule_time TEXT NOT NULL DEFAULT '18:00',
    schedule_tz TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    schedule_days TEXT NOT NULL DEFAULT 'mon,tue,wed,thu,fri',
    range_days INTEGER NOT NULL DEFAULT 1,
    member_ids TEXT[] DEFAULT ARRAY[]::TEXT[],
    project_ids INTEGER[] DEFAULT ARRAY[]::INTEGER[],
    ai_summary_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ai_provider TEXT NOT NULL DEFAULT 'deepseek',
    ai_prompt TEXT DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS publish_jobs_team_idx ON publish_jobs(team_id, active);

export type SectionId =
  | "standups"
  | "members"
  | "reports"
  | "analytics"
  | "settings"
  | "webhooks"
  | "kudos"
  | "automation"
  | "mcp";

export type Member = {
  id: string;
  name: string;
  display_name?: string;
  raw_name?: string;
  avatar?: string;
  email?: string;
  tz?: string;
  role?: "admin" | "member" | string;
  tags?: string[];
};

export type Channel = {
  id: string;
  name: string;
};

export type Standup = {
  id: number;
  name: string;
  channel_id: string;
  schedule_time: string;
  schedule_tz: string;
  schedule_days: string[];
  questions: string[];
  active: boolean;
  participants: string[];
  reminder_minutes: number;
  report_channel?: string;
  report_time?: string;
  group_by?: string;
  post_as?: string;
  sort_order?: string;
  edit_window?: string;
  display_avatar?: boolean;
  jira_base_url?: string;
  zendesk_base_url?: string;
  github_repo?: string;
  linear_team?: string;
  ai_summary_enabled?: boolean;
  ai_provider?: string;
  feed_public?: boolean;
  manager_email?: string;
  manager_digest_enabled?: boolean;
  post_to_thread?: boolean;
  notify_on_report?: boolean;
  post_summary?: boolean;
};

export type SettingsPayload = {
  values: Record<string, string>;
  secret_set: Record<string, boolean>;
};

export type Me = {
  team_id: string;
  user_id: string;
  team_name: string;
  role: string;
};

export type Stats = {
  completion_rate: number;
  active_members: number;
  total_responses: number;
};

export type ReportsPayload = {
  standups?: Array<Record<string, string>>;
  participation?: Array<Record<string, string | number>>;
  total_days?: number;
};

export type Webhook = {
  id: number;
  url: string;
  created_at?: string;
};

export type AutomationRule = {
  id: number;
  name: string;
  trigger_type: string;
  action_type: string;
  target: string;
  active?: boolean;
};

export type McpKey = {
  id: number;
  name: string;
  prefix?: string;
  created_at?: string;
  last_used_at?: string;
};

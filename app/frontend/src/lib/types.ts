import type { ReactNode } from "react";

export type SectionId =
  | "dashboard"
  | "collections"
  | "publish"
  | "integrations"
  | "skills"
  | "manage";

export type NavItem = {
  id: SectionId;
  label: string;
  icon: ReactNode;
};

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

export type Project = {
  id: number;
  name: string;
  description?: string;
  status?: string;
};

export type ProgressCollection = {
  id: number;
  name: string;
  channel_id: string;
  schedule_time: string;
  schedule_tz: string;
  schedule_days: string[];
  questions: string[];
  participants: string[];
  reminder_minutes: number;
  active: boolean;
};

export type ProgressEntry = {
  id: number;
  user_id: string;
  member_name?: string;
  project_id?: number;
  project_name?: string;
  role?: string;
  progress_date?: string;
  content?: string;
  submitted_at?: string;
  updated_at?: string;
};

export type PublishJob = {
  id: number;
  name: string;
  destination_type: "feishu_channel" | "webhook" | string;
  destination: string;
  schedule_time: string;
  schedule_tz: string;
  schedule_days: string[] | string;
  range_days: number;
  member_ids?: string[];
  project_ids?: number[];
  ai_summary_enabled: boolean;
  ai_provider: string;
  ai_prompt?: string;
  active: boolean;
};

export type DataBoard = {
  total_entries: number;
  active_members: number;
  active_projects: number;
  updated_today: number;
  by_project: Array<{ name: string; count: number }>;
  by_member: Array<{ name: string; count: number }>;
  by_date: Array<{ date: string; count: number }>;
  recent_entries: ProgressEntry[];
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

export type SkillsPackage = {
  version: string;
  filename: string;
  download_url: string;
};

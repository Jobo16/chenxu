import type {
  Channel,
  DataBoard,
  Me,
  Member,
  ProgressCollection,
  ProgressEntry,
  Project,
  PublishJob,
  SkillsPackage,
  SettingsPayload,
} from "./types";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/dashboard/api${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401) {
    window.location.href = "/dashboard/login";
    throw new Error("登录已过期");
  }
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.error || res.statusText);
  }
  return res.json();
}

export const api = {
  me: () => request<Me>("GET", "/me"),
  dataBoard: (days = 7) => request<DataBoard>("GET", `/data-board?days=${days}`),
  channels: () => request<Channel[]>("GET", "/channels"),
  members: (channelId?: string) =>
    request<Member[]>("GET", `/members${channelId ? `?channel_id=${encodeURIComponent(channelId)}` : ""}`),
  updateMemberProfile: (id: string, payload: { display_name_override: string; tags: string[] }) =>
    request("PUT", `/members/${encodeURIComponent(id)}`, payload),
  updateMemberRole: (id: string, role: string) => request("PUT", `/members/${encodeURIComponent(id)}/role`, { role }),

  projects: () => request<Project[]>("GET", "/projects"),
  createProject: (payload: Partial<Project>) => request<Project>("POST", "/projects", payload),
  updateProject: (id: number, payload: Partial<Project>) => request<Project>("PUT", `/projects/${id}`, payload),

  collections: () => request<ProgressCollection[]>("GET", "/collections"),
  createCollection: (payload: Partial<ProgressCollection>) => request<ProgressCollection>("POST", "/collections", payload),
  updateCollection: (id: number, payload: Partial<ProgressCollection>) =>
    request<ProgressCollection>("PUT", `/collections/${id}`, payload),
  deleteCollection: (id: number) => request<{ ok: boolean }>("DELETE", `/collections/${id}`),

  progress: (params = new URLSearchParams()) =>
    request<ProgressEntry[]>("GET", `/progress${params.toString() ? `?${params.toString()}` : ""}`),
  createProgress: (payload: Partial<ProgressEntry>) => request<ProgressEntry>("POST", "/progress", payload),
  updateProgress: (id: number, payload: Partial<ProgressEntry>) => request<ProgressEntry>("PUT", `/progress/${id}`, payload),
  progressSnapshots: (id: number) => request<Record<string, unknown>[]>("GET", `/progress/${id}/snapshots`),

  publishJobs: () => request<PublishJob[]>("GET", "/publish-jobs"),
  createPublishJob: (payload: Partial<PublishJob>) => request<PublishJob>("POST", "/publish-jobs", payload),
  updatePublishJob: (id: number, payload: Partial<PublishJob>) => request<PublishJob>("PUT", `/publish-jobs/${id}`, payload),
  deletePublishJob: (id: number) => request<{ ok: boolean }>("DELETE", `/publish-jobs/${id}`),

  settings: () => request<SettingsPayload>("GET", "/settings"),
  saveSettings: (settings: Record<string, string>) => request<SettingsPayload>("PUT", "/settings", { settings }),

  skillsPackage: () => request<SkillsPackage>("GET", "/skills-package"),
};

export function exportProgressCsvUrl() {
  return "/dashboard/api/export/csv";
}

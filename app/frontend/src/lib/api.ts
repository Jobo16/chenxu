import type {
  AutomationRule,
  Channel,
  McpKey,
  Me,
  Member,
  ReportsPayload,
  SettingsPayload,
  Standup,
  Stats,
  Webhook,
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
  stats: () => request<Stats>("GET", "/stats"),
  channels: () => request<Channel[]>("GET", "/channels"),
  standups: () => request<Standup[]>("GET", "/standups"),
  createStandup: (payload: Partial<Standup>) => request<Standup>("POST", "/standups", payload),
  updateStandup: (id: number, payload: Partial<Standup>) => request<Standup>("PUT", `/standups/${id}`, payload),
  deleteStandup: (id: number) => request<{ ok: boolean }>("DELETE", `/standups/${id}`),
  members: (channelId?: string) =>
    request<Member[]>("GET", `/members${channelId ? `?channel_id=${encodeURIComponent(channelId)}` : ""}`),
  updateMemberProfile: (id: string, payload: { display_name_override: string; tags: string[] }) =>
    request("PUT", `/members/${encodeURIComponent(id)}`, payload),
  updateMemberRole: (id: string, role: string) => request("PUT", `/members/${encodeURIComponent(id)}/role`, { role }),
  inviteAdmin: (userId: string) => request("POST", "/members/invite", { user_id: userId, role: "admin" }),
  settings: () => request<SettingsPayload>("GET", "/settings"),
  saveSettings: (settings: Record<string, string>) => request<SettingsPayload>("PUT", "/settings", { settings }),
  reports: (params: URLSearchParams) => request<ReportsPayload>("GET", `/reports?${params.toString()}`),
  webhooks: () => request<Webhook[]>("GET", "/webhooks"),
  addWebhook: (url: string) => request<Webhook>("POST", "/webhooks", { url }),
  deleteWebhook: (id: number) => request<{ ok: boolean }>("DELETE", `/webhooks/${id}`),
  analytics: (days: number) => request<Record<string, unknown>>("GET", `/analytics?days=${days}`),
  kudos: () => request<Record<string, unknown>[]>("GET", "/kudos"),
  kudosLeaderboard: () => request<Record<string, unknown>[]>("GET", "/kudos/leaderboard"),
  templates: () => request<Array<{ id?: string; name: string; questions: string[] }>>("GET", "/templates"),
  rules: () => request<AutomationRule[]>("GET", "/rules"),
  createRule: (payload: Partial<AutomationRule> & { condition_value?: string; message_template?: string }) =>
    request<AutomationRule>("POST", "/rules", payload),
  deleteRule: (id: number) => request<{ ok: boolean }>("DELETE", `/rules/${id}`),
  mcpKeys: async () => {
    const payload = await request<{ keys: McpKey[] }>("GET", "/mcp/keys");
    return payload.keys || [];
  },
  createMcpKey: (name: string) => request<{ key: string; message?: string }>("POST", "/mcp/keys", { name }),
  deleteMcpKey: (id: number) => request<{ ok: boolean }>("DELETE", `/mcp/keys/${id}`),
  createFeedToken: () => request<{ token: string }>("POST", "/feed-token"),
  disableFeedToken: () => request<{ ok: boolean }>("DELETE", "/feed-token"),
};

export function exportCsvUrl() {
  return "/dashboard/api/export/csv";
}

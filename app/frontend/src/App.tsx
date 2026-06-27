import * as Dialog from "@radix-ui/react-dialog";
import * as Switch from "@radix-ui/react-switch";
import {
  BarChart3,
  Bot,
  CalendarDays,
  ChevronDown,
  CirclePlus,
  Download,
  Edit3,
  KeyRound,
  Link2,
  Loader2,
  MessageCircle,
  RefreshCw,
  Search,
  Settings,
  Sparkles,
  Trash2,
  Trophy,
  Users,
  Zap,
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api, exportCsvUrl } from "./lib/api";
import type { AutomationRule, Channel, McpKey, Me, Member, ReportsPayload, SectionId, SettingsPayload, Standup, Stats, Webhook } from "./lib/types";

const navItems: Array<{ id: SectionId; label: string; icon: ReactNode }> = [
  { id: "standups", label: "站会", icon: <CalendarDays /> },
  { id: "members", label: "成员", icon: <Users /> },
  { id: "reports", label: "汇总", icon: <BarChart3 /> },
  { id: "analytics", label: "分析", icon: <Search /> },
  { id: "settings", label: "设置", icon: <Settings /> },
  { id: "webhooks", label: "Webhook", icon: <Link2 /> },
  { id: "kudos", label: "表扬", icon: <Trophy /> },
  { id: "automation", label: "自动化", icon: <Zap /> },
  { id: "mcp", label: "MCP", icon: <KeyRound /> },
];

const dayOptions = [
  ["mon", "周一"],
  ["tue", "周二"],
  ["wed", "周三"],
  ["thu", "周四"],
  ["fri", "周五"],
  ["sat", "周六"],
  ["sun", "周日"],
];

const defaultQuestions = ["昨天完成了什么？", "今天计划做什么？", "有什么阻塞？没有就回复“无”。"];

type StandupForm = {
  id?: number;
  name: string;
  channel_id: string;
  participants: string[];
  schedule_time: string;
  schedule_tz: string;
  schedule_days: string[];
  questions: string[];
  reminder_minutes: number;
  report_channel: string;
  report_time: string;
  post_to_thread: boolean;
  notify_on_report: boolean;
  ai_summary_enabled: boolean;
  ai_provider: string;
};

const emptyStandupForm = (): StandupForm => ({
  name: "每日站会",
  channel_id: "",
  participants: [],
  schedule_time: "09:30",
  schedule_tz: "Asia/Shanghai",
  schedule_days: ["mon", "tue", "wed", "thu", "fri"],
  questions: [...defaultQuestions],
  reminder_minutes: 0,
  report_channel: "",
  report_time: "",
  post_to_thread: false,
  notify_on_report: true,
  ai_summary_enabled: true,
  ai_provider: "deepseek",
});

function App() {
  const [section, setSection] = useState<SectionId>("standups");
  const [me, setMe] = useState<Me | null>(null);
  const [stats, setStats] = useState<Stats>({ completion_rate: 0, active_members: 0, total_responses: 0 });
  const [standups, setStandups] = useState<Standup[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [standupModalOpen, setStandupModalOpen] = useState(false);
  const [standupForm, setStandupForm] = useState<StandupForm>(emptyStandupForm);
  const [memberEditor, setMemberEditor] = useState<Member | null>(null);

  useEffect(() => {
    bootstrap();
  }, []);

  async function bootstrap() {
    setLoading(true);
    try {
      const [meRes, statsRes, standupsRes, channelsRes, membersRes] = await Promise.all([
        api.me(),
        api.stats().catch(() => ({ completion_rate: 0, active_members: 0, total_responses: 0 })),
        api.standups(),
        api.channels().catch(() => []),
        api.members().catch(() => []),
      ]);
      setMe(meRes);
      setStats(statsRes);
      setStandups(standupsRes);
      setChannels(channelsRes);
      setMembers(membersRes);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "控制台加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function refreshStandups() {
    const [statsRes, standupsRes] = await Promise.all([api.stats(), api.standups()]);
    setStats(statsRes);
    setStandups(standupsRes);
  }

  async function refreshMembers(channelId?: string) {
    const res = await api.members(channelId);
    setMembers(res);
    return res;
  }

  function openCreateStandup() {
    setStandupForm(emptyStandupForm());
    setStandupModalOpen(true);
  }

  function openEditStandup(standup: Standup) {
    setStandupForm({
      id: standup.id,
      name: standup.name || "每日站会",
      channel_id: standup.channel_id || "",
      participants: standup.participants || [],
      schedule_time: standup.schedule_time || "09:30",
      schedule_tz: standup.schedule_tz || "Asia/Shanghai",
      schedule_days: standup.schedule_days?.length ? standup.schedule_days : ["mon", "tue", "wed", "thu", "fri"],
      questions: standup.questions?.length ? standup.questions : [...defaultQuestions],
      reminder_minutes: standup.reminder_minutes || 0,
      report_channel: standup.report_channel || "",
      report_time: standup.report_time || "",
      post_to_thread: !!standup.post_to_thread,
      notify_on_report: standup.notify_on_report !== false,
      ai_summary_enabled: !!standup.ai_summary_enabled,
      ai_provider: standup.ai_provider || "deepseek",
    });
    setStandupModalOpen(true);
  }

  async function saveStandup(event: FormEvent) {
    event.preventDefault();
    const payload = {
      ...standupForm,
      questions: standupForm.questions.map((q) => q.trim()).filter(Boolean),
      post_summary: standupForm.ai_summary_enabled,
    };
    try {
      if (standupForm.id) {
        await api.updateStandup(standupForm.id, payload);
        toast.success("站会已保存");
      } else {
        await api.createStandup(payload);
        toast.success("站会已创建");
      }
      setStandupModalOpen(false);
      await refreshStandups();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  }

  async function toggleStandup(standup: Standup, active: boolean) {
    try {
      await api.updateStandup(standup.id, { active });
      setStandups((list) => list.map((item) => (item.id === standup.id ? { ...item, active } : item)));
      toast.success(active ? "站会已启用" : "站会已暂停");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "操作失败");
    }
  }

  async function deleteStandup(standup: Standup) {
    if (!window.confirm(`确定删除「${standup.name}」吗？`)) return;
    try {
      await api.deleteStandup(standup.id);
      setStandups((list) => list.filter((item) => item.id !== standup.id));
      toast.success("站会已删除");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "删除失败");
    }
  }

  const currentTitle = navItems.find((item) => item.id === section)?.label || "站会";
  const currentSubtitle: Record<SectionId, string> = {
    standups: "管理每日进度收集和汇总",
    members: "团队成员、标签和控制台权限",
    reports: "查看历史进度和每日汇总",
    analytics: "成员参与趋势和完成情况",
    settings: "飞书、AI 和控制台配置",
    webhooks: "站会完成后推送 HTTP 通知",
    kudos: "记录团队认可",
    automation: "配置触发条件和动作",
    mcp: "让 AI 助手查询站会数据",
  };

  return (
    <div className="app-shell">
      <Sidebar section={section} onSelect={setSection} teamName={me?.team_name || "晨序"} />
      <main className="main">
        <Topbar title={currentTitle} subtitle={currentSubtitle[section]}>
          {section === "standups" && <Button onClick={openCreateStandup} icon={<CirclePlus />}>新建站会</Button>}
          {section === "members" && (
            <div className="actions">
              <Button variant="secondary" onClick={() => refreshMembers().then(() => toast.success("成员已刷新"))} icon={<RefreshCw />}>刷新</Button>
            </div>
          )}
          {section === "reports" && <Button variant="secondary" onClick={() => (window.location.href = exportCsvUrl())} icon={<Download />}>导出 CSV</Button>}
        </Topbar>
        {loading ? (
          <Loading />
        ) : (
          <>
            {section === "standups" && (
              <StandupsPage
                stats={stats}
                standups={standups}
                channels={channels}
                onCreate={openCreateStandup}
                onEdit={openEditStandup}
                onDelete={deleteStandup}
                onToggle={toggleStandup}
              />
            )}
            {section === "members" && (
              <MembersPage
                members={members}
                me={me}
                onEdit={setMemberEditor}
                onRefresh={refreshMembers}
                setMembers={setMembers}
              />
            )}
            {section === "reports" && <ReportsPage members={members} />}
            {section === "analytics" && <AnalyticsPage />}
            {section === "settings" && (
              <SettingsPage
                channels={channels}
                members={members}
                setChannels={setChannels}
                setMembers={setMembers}
                onEditFirstStandup={() => {
                  if (standups[0]) openEditStandup(standups[0]);
                  else openCreateStandup();
                }}
              />
            )}
            {section === "webhooks" && <WebhooksPage />}
            {section === "kudos" && <KudosPage />}
            {section === "automation" && <AutomationPage />}
            {section === "mcp" && <McpPage />}
          </>
        )}
      </main>
      <FloatingDecor />
      <StandupDialog
        open={standupModalOpen}
        onOpenChange={setStandupModalOpen}
        form={standupForm}
        setForm={setStandupForm}
        channels={channels}
        members={members}
        onSubmit={saveStandup}
      />
      <MemberDialog
        member={memberEditor}
        onOpenChange={(open) => !open && setMemberEditor(null)}
        onSaved={async () => {
          setMemberEditor(null);
          await refreshMembers();
        }}
      />
    </div>
  );
}

function Sidebar({ section, onSelect, teamName }: { section: SectionId; onSelect: (id: SectionId) => void; teamName: string }) {
  return (
    <aside className="sidebar">
      <div className="brand-box">
        <div className="brand-mark"><SunIcon /></div>
        <div>
          <div className="brand-title">晨序</div>
          <div className="brand-subtitle">控制台</div>
        </div>
      </div>
      <div className="nav-label">工作台</div>
      <nav className="nav-list">
        {navItems.slice(0, 4).map((item) => (
          <button key={item.id} className={`nav-button ${section === item.id ? "active" : ""}`} onClick={() => onSelect(item.id)}>
            <span className="nav-icon">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="nav-label">配置</div>
      <nav className="nav-list">
        {navItems.slice(4).map((item) => (
          <button key={item.id} className={`nav-button ${section === item.id ? "active" : ""}`} onClick={() => onSelect(item.id)}>
            <span className="nav-icon">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-card">
        <div className="avatar-letter">{teamName[0]?.toUpperCase() || "晨"}</div>
        <div>
          <div className="workspace-name">{teamName}</div>
          <a href="/dashboard/logout">退出</a>
        </div>
      </div>
    </aside>
  );
}

function Topbar({ title, subtitle, children }: { title: string; subtitle: string; children?: ReactNode }) {
  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className="topbar-actions">{children}</div>
    </header>
  );
}

function StandupsPage({
  stats,
  standups,
  channels,
  onCreate,
  onEdit,
  onDelete,
  onToggle,
}: {
  stats: Stats;
  standups: Standup[];
  channels: Channel[];
  onCreate: () => void;
  onEdit: (s: Standup) => void;
  onDelete: (s: Standup) => void;
  onToggle: (s: Standup, active: boolean) => void;
}) {
  const channelName = (id: string) => channels.find((c) => c.id === id)?.name || id || "未设置";
  return (
    <section className="content-stack">
      <div className="stats-grid">
        <StatCard tone="yellow" label="完成率" value={`${stats.completion_rate || 0}%`} helper="最近 7 天" icon={<Sparkles />} />
        <StatCard tone="mint" label="活跃成员" value={String(stats.active_members || 0)} helper="本周已提交" icon={<Users />} />
        <StatCard tone="red" label="本周提交" value={String(stats.total_responses || 0)} helper="累计提交" icon={<MessageCircle />} />
      </div>
      {!standups.length ? (
        <EmptyState title="还没有站会" description="创建一个站会开始收集团队进度。" action={<Button onClick={onCreate} icon={<CirclePlus />}>新建站会</Button>} />
      ) : (
        <div className="standup-list">
          {standups.map((standup) => (
            <article className="standup-row" key={standup.id}>
              <div className="row-icon"><CalendarDays /></div>
              <div className="row-main">
                <div className="row-title">{standup.name || "每日站会"}</div>
                <div className="row-meta">
                  <span>#{channelName(standup.channel_id)}</span>
                  <span>{standup.schedule_time} {standup.schedule_tz}</span>
                  <span>{standup.schedule_days?.map((d) => dayOptions.find(([id]) => id === d)?.[1] || d).join("、")}</span>
                </div>
              </div>
              <Badge tone={standup.active ? "green" : "gray"}>{standup.active ? "启用" : "暂停"}</Badge>
              <Switch.Root className="switch" checked={standup.active} onCheckedChange={(value) => onToggle(standup, value)}>
                <Switch.Thumb className="switch-thumb" />
              </Switch.Root>
              <Button size="sm" variant="secondary" onClick={() => onEdit(standup)} icon={<Edit3 />}>编辑</Button>
              <Button size="sm" variant="danger" onClick={() => onDelete(standup)} icon={<Trash2 />}>删除</Button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function MembersPage({
  members,
  me,
  onEdit,
  onRefresh,
  setMembers,
}: {
  members: Member[];
  me: Me | null;
  onEdit: (m: Member) => void;
  onRefresh: () => Promise<Member[]>;
  setMembers: (members: Member[]) => void;
}) {
  async function setRole(member: Member, role: string) {
    try {
      await api.updateMemberRole(member.id, role);
      setMembers(members.map((item) => (item.id === member.id ? { ...item, role } : item)));
      toast.success(role === "admin" ? "已设为管理员" : "已设为成员");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "权限更新失败");
    }
  }

  return (
    <section className="members-grid">
      {!members.length ? (
        <EmptyState title="没有找到成员" description="先在设置页连接飞书并选择群聊。" />
      ) : (
        members.map((member) => (
          <article className="member-card" key={member.id}>
            <Avatar member={member} />
            <div className="member-body">
              <div className="member-name">{member.name || member.display_name || member.id}</div>
              {member.raw_name && member.raw_name !== member.name && <div className="member-raw">{member.raw_name}</div>}
              <div className="member-raw">{member.tz || "Asia/Shanghai"}</div>
              {!!member.tags?.length && <div className="tag-row">{member.tags.map((tag) => <span key={tag} className="tag">{tag}</span>)}</div>}
              <div className="member-actions">
                <Badge tone={member.role === "admin" ? "green" : "gray"}>{member.role === "admin" ? "管理员" : "成员"}</Badge>
                {me?.role === "admin" && <button className="text-button" onClick={() => onEdit(member)}>编辑</button>}
                {me?.role === "admin" && member.id !== me.user_id && (
                  <button className="text-button" onClick={() => setRole(member, member.role === "admin" ? "member" : "admin")}>
                    {member.role === "admin" ? "设为成员" : "设为管理员"}
                  </button>
                )}
              </div>
            </div>
          </article>
        ))
      )}
    </section>
  );
}

function ReportsPage({ members }: { members: Member[] }) {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [userId, setUserId] = useState("");
  const [data, setData] = useState<ReportsPayload>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    load();
  }, [dateFrom, dateTo, userId]);

  async function load() {
    setLoading(true);
    const params = new URLSearchParams();
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    if (userId) params.set("user_id", userId);
    try {
      setData(await api.reports(params));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "汇总加载失败");
    } finally {
      setLoading(false);
    }
  }

  const memberLookup = useMemo(() => new Map(members.map((m) => [m.id, m])), [members]);
  const standups = data.standups || [];
  const participation = data.participation || [];

  return (
    <section className="content-stack">
      <div className="filter-bar">
        <label>从<input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label>
        <label>到<input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label>
        <label>成员
          <select value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">全部成员</option>
            {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </label>
        <Button variant="secondary" onClick={() => { setDateFrom(""); setDateTo(""); setUserId(""); }}>重置</Button>
      </div>
      {loading ? <Loading /> : (
        <>
          <Panel title={`参与情况 - 最近 ${data.total_days || 7} 天`}>
            <DataTable
              headers={["姓名", "参与", "近期完成"]}
              rows={participation.map((p) => [
                memberLookup.get(String(p.user_id))?.name || String(p.name || p.user_id || ""),
                `${p.responses || 0}/${p.total || 0}`,
                "★".repeat(Number(p.stars || 0)) + "☆".repeat(Math.max(0, 5 - Number(p.stars || 0))),
              ])}
              empty="暂无参与数据"
            />
          </Panel>
          <Panel title="站会回复">
            <div className="report-list">
              {standups.length ? standups.map((row, index) => (
                <article className="report-row" key={`${row.user_id}-${row.submitted_at}-${index}`}>
                  <div className="report-person">{memberLookup.get(String(row.user_id))?.name || row.user_name || row.user_id}</div>
                  <div className="report-copy">
                    <div><strong>昨天：</strong>{row.yesterday || "-"}</div>
                    <div><strong>今天：</strong>{row.today || "-"}</div>
                    {row.blockers && String(row.blockers).toLowerCase() !== "none" && <div className="danger-text"><strong>阻塞：</strong>{row.blockers}</div>}
                  </div>
                </article>
              )) : <div className="empty-line">当前筛选条件下没有回复。</div>}
            </div>
          </Panel>
        </>
      )}
    </section>
  );
}

function SettingsPage({
  channels,
  members,
  setChannels,
  setMembers,
  onEditFirstStandup,
}: {
  channels: Channel[];
  members: Member[];
  setChannels: (channels: Channel[]) => void;
  setMembers: (members: Member[]) => void;
  onEditFirstStandup: () => void;
}) {
  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      const payload = await api.settings();
      setSettings(payload);
      setValues(payload.values || {});
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "设置加载失败");
    } finally {
      setLoading(false);
    }
  }

  function set(key: string, value: string) {
    setValues((old) => ({ ...old, [key]: value }));
  }

  function collect() {
    const next = { ...values };
    const chat = channels.find((c) => c.id === next.FEISHU_DEFAULT_CHAT_ID);
    if (chat) next.FEISHU_DEFAULT_CHAT_NAME = chat.name;
    if (channels.length) next.FEISHU_CHANNELS = channels.map((c) => `${c.id}|${c.name || c.id}`).join(",");
    if (members.length) {
      next.FEISHU_STANDUP_MEMBERS = members.map((m) => [m.id, m.name || m.display_name || "", m.email || ""].filter(Boolean).join("|")).join(",");
    }
    return next;
  }

  async function save(showMessage = true) {
    const payload = await api.saveSettings(collect());
    setSettings(payload);
    setValues(payload.values || {});
    if (showMessage) toast.success("设置已保存");
    return payload;
  }

  async function connectFeishu() {
    try {
      await save(false);
      const ch = await api.channels();
      setChannels(ch);
      if (ch[0]?.id) {
        const list = await api.members(ch[0].id);
        setMembers(list);
      }
      toast.success(ch.length ? "飞书连接成功" : "凭证已保存，请先把机器人拉进群");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "飞书连接失败");
    }
  }

  async function syncMembers(chatId = values.FEISHU_DEFAULT_CHAT_ID) {
    if (!chatId) {
      toast.error("请先选择群聊");
      return;
    }
    try {
      const list = await api.members(chatId);
      setMembers(list);
      toast.success(list.length ? "成员已同步" : "这个群里还没有可同步成员");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "成员同步失败");
    }
  }

  if (loading || !settings) return <Loading />;
  const secret = settings.secret_set || {};
  const hasCreds = Boolean(values.FEISHU_APP_ID || secret.FEISHU_APP_SECRET);

  return (
    <section className="settings-layout">
      <Panel title="系统设置" icon={<Bot />}>
        <div className="form-grid">
          <Field label="公开访问地址"><input value={values.APP_URL || ""} onChange={(e) => set("APP_URL", e.target.value)} placeholder="http://localhost:3000" /></Field>
          <Field label="控制台访问方式">
            <select value={values.DASHBOARD_AUTH || "none"} onChange={(e) => set("DASHBOARD_AUTH", e.target.value)}>
              <option value="none">内部直进</option>
              <option value="key">访问密钥</option>
            </select>
          </Field>
          <Field label="控制台访问密钥"><input type="password" value={values.DASHBOARD_ADMIN_KEY || ""} onChange={(e) => set("DASHBOARD_ADMIN_KEY", e.target.value)} placeholder={secret.DASHBOARD_ADMIN_KEY ? "已配置，留空不变" : "未配置"} /></Field>
        </div>
      </Panel>
      <Panel title="飞书机器人" icon={<MessageCircle />}>
        <div className={`status-box ${hasCreds ? "ok" : ""}`}>
          {hasCreds ? "凭证已保存。可以连接飞书并拉取群聊、成员。" : "先填写 App ID 和 App Secret，然后点击连接飞书。"}
        </div>
        <div className="form-grid">
          <Field label="事件接收方式">
            <select value={values.FEISHU_EVENT_MODE || "ws"} onChange={(e) => set("FEISHU_EVENT_MODE", e.target.value)}>
              <option value="ws">长连接</option>
              <option value="webhook">公网回调</option>
            </select>
          </Field>
          <Field label="App ID"><input value={values.FEISHU_APP_ID || ""} onChange={(e) => set("FEISHU_APP_ID", e.target.value)} placeholder="cli_xxx" /></Field>
          <Field label="App Secret"><input type="password" value={values.FEISHU_APP_SECRET || ""} onChange={(e) => set("FEISHU_APP_SECRET", e.target.value)} placeholder={secret.FEISHU_APP_SECRET ? "已配置，留空不变" : "未配置"} /></Field>
          <Field label="工作区名称"><input value={values.FEISHU_TEAM_NAME || ""} onChange={(e) => set("FEISHU_TEAM_NAME", e.target.value)} placeholder="飞书工作区" /></Field>
          <Field label="默认群聊">
            <select value={values.FEISHU_DEFAULT_CHAT_ID || ""} onChange={(e) => { set("FEISHU_DEFAULT_CHAT_ID", e.target.value); syncMembers(e.target.value); }}>
              <option value="">{channels.length ? "选择默认群聊" : "先连接飞书并拉取群聊"}</option>
              {channels.map((c) => <option key={c.id} value={c.id}>#{c.name || c.id}</option>)}
            </select>
          </Field>
          <Field label="管理员">
            <select value={values.FEISHU_ADMIN_OPEN_ID || ""} onChange={(e) => set("FEISHU_ADMIN_OPEN_ID", e.target.value)}>
              <option value="">选择管理员</option>
              {members.map((m) => <option key={m.id} value={m.id}>{m.name || m.id}</option>)}
            </select>
          </Field>
          <Field label="默认收集时间"><input type="time" value={values.FEISHU_SCHEDULE_TIME || "09:30"} onChange={(e) => set("FEISHU_SCHEDULE_TIME", e.target.value)} /></Field>
          <Field label="默认时区"><input value={values.FEISHU_SCHEDULE_TZ || "Asia/Shanghai"} onChange={(e) => set("FEISHU_SCHEDULE_TZ", e.target.value)} /></Field>
          <Field label="默认工作日"><input value={values.FEISHU_SCHEDULE_DAYS || "mon,tue,wed,thu,fri"} onChange={(e) => set("FEISHU_SCHEDULE_DAYS", e.target.value)} /></Field>
        </div>
        <div className="actions">
          <Button onClick={connectFeishu} icon={<RefreshCw />}>连接飞书</Button>
          <Button variant="secondary" onClick={() => syncMembers()} icon={<Users />}>同步成员</Button>
          <Button variant="secondary" onClick={onEditFirstStandup} icon={<CalendarDays />}>站会配置</Button>
        </div>
      </Panel>
      <Panel title="AI 汇总" icon={<Sparkles />}>
        <div className="form-grid">
          <Field label="默认 AI 汇总">
            <select value={values.FEISHU_AI_SUMMARY_ENABLED || "false"} onChange={(e) => set("FEISHU_AI_SUMMARY_ENABLED", e.target.value)}>
              <option value="true">开启</option>
              <option value="false">关闭</option>
            </select>
          </Field>
          <Field label="AI 服务">
            <select value={values.FEISHU_AI_PROVIDER || "openai"} onChange={(e) => set("FEISHU_AI_PROVIDER", e.target.value)}>
              <option value="openai">OpenAI</option>
              <option value="deepseek">DeepSeek</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </Field>
          <Field label="OpenAI API Key"><input type="password" value={values.OPENAI_API_KEY || ""} onChange={(e) => set("OPENAI_API_KEY", e.target.value)} placeholder={secret.OPENAI_API_KEY ? "已配置，留空不变" : "未配置"} /></Field>
          <Field label="DeepSeek API Key"><input type="password" value={values.DEEPSEEK_API_KEY || ""} onChange={(e) => set("DEEPSEEK_API_KEY", e.target.value)} placeholder={secret.DEEPSEEK_API_KEY ? "已配置，留空不变" : "未配置"} /></Field>
          <Field label="Anthropic API Key"><input type="password" value={values.ANTHROPIC_API_KEY || ""} onChange={(e) => set("ANTHROPIC_API_KEY", e.target.value)} placeholder={secret.ANTHROPIC_API_KEY ? "已配置，留空不变" : "未配置"} /></Field>
          <Field label="DeepSeek Base URL"><input value={values.DEEPSEEK_BASE_URL || "https://api.deepseek.com"} onChange={(e) => set("DEEPSEEK_BASE_URL", e.target.value)} /></Field>
          <Field label="DeepSeek 模型"><input value={values.DEEPSEEK_MODEL || "deepseek-chat"} onChange={(e) => set("DEEPSEEK_MODEL", e.target.value)} /></Field>
        </div>
        <div className="actions"><Button onClick={() => save()}>保存设置</Button></div>
      </Panel>
    </section>
  );
}

function WebhooksPage() {
  const [hooks, setHooks] = useState<Webhook[]>([]);
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.webhooks().then(setHooks).catch((e) => toast.error(e.message)).finally(() => setLoading(false));
  }, []);

  async function add() {
    if (!url.trim()) return toast.error("请输入 URL");
    try {
      const hook = await api.addWebhook(url.trim());
      setHooks((list) => [...list, hook]);
      setUrl("");
      toast.success("Webhook 已添加");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "添加失败");
    }
  }

  async function remove(id: number) {
    if (!window.confirm("确定删除这个 Webhook 吗？")) return;
    await api.deleteWebhook(id);
    setHooks((list) => list.filter((hook) => hook.id !== id));
  }

  return (
    <section className="content-stack">
      <Panel title="Webhook">
        {loading ? <Loading /> : <DataTable headers={["URL", "添加时间", ""]} rows={hooks.map((h) => [h.url, h.created_at ? new Date(h.created_at).toLocaleDateString() : "", <Button key={h.id} size="sm" variant="danger" onClick={() => remove(h.id)}>删除</Button>])} empty="还没有 Webhook" />}
      </Panel>
      <div className="inline-form">
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/webhook" />
        <Button onClick={add} icon={<CirclePlus />}>添加 Webhook</Button>
      </div>
    </section>
  );
}

function AutomationPage() {
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState("blocker_detected");
  const [action, setAction] = useState("post_to_channel");
  const [target, setTarget] = useState("");

  useEffect(() => {
    api.rules().then(setRules).catch((e) => toast.error(e.message));
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      const rule = await api.createRule({ name, trigger_type: trigger, action_type: action, target });
      setRules((list) => [...list, rule]);
      setName("");
      setTarget("");
      toast.success("规则已创建");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  }

  async function remove(id: number) {
    await api.deleteRule(id);
    setRules((list) => list.filter((rule) => rule.id !== id));
  }

  return (
    <section className="content-stack">
      <Panel title="自动化规则">
        <DataTable headers={["名称", "触发", "动作", "目标", ""]} rows={rules.map((r) => [r.name, r.trigger_type, r.action_type, r.target, <Button key={r.id} size="sm" variant="danger" onClick={() => remove(r.id)}>删除</Button>])} empty="暂无规则" />
      </Panel>
      <Panel title="新建规则">
        <form className="form-grid" onSubmit={save}>
          <Field label="规则名称"><input value={name} onChange={(e) => setName(e.target.value)} required placeholder="阻塞提醒" /></Field>
          <Field label="触发条件"><select value={trigger} onChange={(e) => setTrigger(e.target.value)}><option value="blocker_detected">发现阻塞</option><option value="low_participation">参与率过低</option><option value="standup_complete">站会完成</option></select></Field>
          <Field label="动作"><select value={action} onChange={(e) => setAction(e.target.value)}><option value="post_to_channel">发送到群聊</option><option value="send_dm">发送私聊</option><option value="fire_webhook">调用 Webhook</option></select></Field>
          <Field label="目标"><input value={target} onChange={(e) => setTarget(e.target.value)} required placeholder="oc_xxx 或 https://..." /></Field>
          <div className="form-submit"><Button>保存规则</Button></div>
        </form>
      </Panel>
    </section>
  );
}

function AnalyticsPage() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    api.analytics(days).then(setData).catch((e) => toast.error(e.message));
  }, [days]);
  return (
    <section className="content-stack">
      <div className="segmented"><button className={days === 7 ? "active" : ""} onClick={() => setDays(7)}>7 天</button><button className={days === 30 ? "active" : ""} onClick={() => setDays(30)}>30 天</button></div>
      <Panel title="参与分析">
        <pre className="json-preview">{JSON.stringify(data || {}, null, 2)}</pre>
      </Panel>
    </section>
  );
}

function KudosPage() {
  const [feed, setFeed] = useState<Record<string, unknown>[]>([]);
  const [board, setBoard] = useState<Record<string, unknown>[]>([]);
  useEffect(() => {
    Promise.all([api.kudos(), api.kudosLeaderboard()]).then(([k, b]) => { setFeed(k); setBoard(b); }).catch((e) => toast.error(e.message));
  }, []);
  return (
    <section className="two-column">
      <Panel title="最近 30 天排行"><pre className="json-preview">{JSON.stringify(board, null, 2)}</pre></Panel>
      <Panel title="最近表扬"><pre className="json-preview">{JSON.stringify(feed, null, 2)}</pre></Panel>
    </section>
  );
}

function McpPage() {
  const [keys, setKeys] = useState<McpKey[]>([]);
  const [name, setName] = useState("Claude Desktop");
  const [newKey, setNewKey] = useState("");
  useEffect(() => {
    api.mcpKeys().then(setKeys).catch((e) => toast.error(e.message));
  }, []);
  async function create() {
    const res = await api.createMcpKey(name);
    setNewKey(res.key);
    setKeys(await api.mcpKeys());
  }
  async function remove(id: number) {
    await api.deleteMcpKey(id);
    setKeys((list) => list.filter((key) => key.id !== id));
  }
  return (
    <section className="content-stack">
      <Panel title="API 密钥">
        <DataTable headers={["名称", "前缀", "创建时间", ""]} rows={keys.map((k) => [k.name, k.prefix || "", k.created_at ? new Date(k.created_at).toLocaleDateString() : "", <Button key={k.id} size="sm" variant="danger" onClick={() => remove(k.id)}>删除</Button>])} empty="暂无密钥" />
        <div className="inline-form pad-top"><input value={name} onChange={(e) => setName(e.target.value)} /><Button onClick={create} icon={<KeyRound />}>生成新密钥</Button></div>
        {newKey && <div className="secret-result"><code>{newKey}</code><Button size="sm" variant="secondary" onClick={() => navigator.clipboard.writeText(newKey)}>复制</Button></div>}
      </Panel>
      <Panel title="客户端配置">
        <pre className="json-preview">{`{
  "mcpServers": {
    "chenxu": {
      "url": "${window.location.origin}/mcp",
      "headers": {
        "Authorization": "Bearer mrn_YOUR_KEY_HERE"
      }
    }
  }
}`}</pre>
      </Panel>
    </section>
  );
}

function StandupDialog({
  open,
  onOpenChange,
  form,
  setForm,
  channels,
  members,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  form: StandupForm;
  setForm: (updater: StandupForm | ((old: StandupForm) => StandupForm)) => void;
  channels: Channel[];
  members: Member[];
  onSubmit: (event: FormEvent) => void;
}) {
  function set<K extends keyof StandupForm>(key: K, value: StandupForm[K]) {
    setForm((old) => ({ ...old, [key]: value }));
  }
  function toggleDay(day: string) {
    set("schedule_days", form.schedule_days.includes(day) ? form.schedule_days.filter((d) => d !== day) : [...form.schedule_days, day]);
  }
  function toggleParticipant(id: string) {
    set("participants", form.participants.includes(id) ? form.participants.filter((p) => p !== id) : [...form.participants, id]);
  }
  function setQuestion(index: number, value: string) {
    set("questions", form.questions.map((q, i) => (i === index ? value : q)));
  }
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content">
          <Dialog.Title className="dialog-title">{form.id ? "编辑站会" : "新建站会"}</Dialog.Title>
          <form onSubmit={onSubmit} className="dialog-body">
            <div className="form-grid">
              <Field label="名称"><input value={form.name} onChange={(e) => set("name", e.target.value)} required /></Field>
              <Field label="群聊"><select value={form.channel_id} onChange={(e) => set("channel_id", e.target.value)}><option value="">选择群聊</option>{channels.map((c) => <option key={c.id} value={c.id}>#{c.name || c.id}</option>)}</select></Field>
              <Field label="时间"><input type="time" value={form.schedule_time} onChange={(e) => set("schedule_time", e.target.value)} /></Field>
              <Field label="时区"><input value={form.schedule_tz} onChange={(e) => set("schedule_tz", e.target.value)} /></Field>
              <Field label="汇总群聊"><select value={form.report_channel} onChange={(e) => set("report_channel", e.target.value)}><option value="">同站会群聊</option>{channels.map((c) => <option key={c.id} value={c.id}>#{c.name || c.id}</option>)}</select></Field>
              <Field label="汇总时间"><input type="time" value={form.report_time} onChange={(e) => set("report_time", e.target.value)} /></Field>
            </div>
            <Field label="工作日"><div className="chip-row">{dayOptions.map(([id, label]) => <button type="button" key={id} className={`chip ${form.schedule_days.includes(id) ? "active" : ""}`} onClick={() => toggleDay(id)}>{label}</button>)}</div></Field>
            <Field label="参与成员"><div className="participant-grid">{members.map((m) => <button type="button" key={m.id} className={`participant ${form.participants.includes(m.id) ? "active" : ""}`} onClick={() => toggleParticipant(m.id)}>{m.name || m.id}</button>)}</div></Field>
            <Field label="问题">{form.questions.map((q, i) => <div className="question-line" key={i}><input value={q} onChange={(e) => setQuestion(i, e.target.value)} /><button type="button" onClick={() => set("questions", form.questions.filter((_, idx) => idx !== i))}>删除</button></div>)}<button type="button" className="add-line" onClick={() => set("questions", [...form.questions, ""])}>添加问题</button></Field>
            <div className="form-grid">
              <Field label="提醒"><select value={form.reminder_minutes} onChange={(e) => set("reminder_minutes", Number(e.target.value))}><option value={0}>不提醒</option><option value={30}>提前 30 分钟</option><option value={60}>提前 1 小时</option><option value={-1}>周末前提醒</option></select></Field>
              <Field label="AI 服务"><select value={form.ai_provider} onChange={(e) => set("ai_provider", e.target.value)}><option value="openai">OpenAI</option><option value="deepseek">DeepSeek</option><option value="anthropic">Anthropic</option></select></Field>
            </div>
            <div className="switch-row"><Toggle checked={form.ai_summary_enabled} onChange={(v) => set("ai_summary_enabled", v)} label="开启 AI 汇总" /><Toggle checked={form.notify_on_report} onChange={(v) => set("notify_on_report", v)} label="汇总时提醒成员" /><Toggle checked={form.post_to_thread} onChange={(v) => set("post_to_thread", v)} label="作为线程回复" /></div>
            <div className="dialog-actions"><Dialog.Close asChild><Button type="button" variant="secondary">取消</Button></Dialog.Close><Button type="submit">保存</Button></div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function MemberDialog({ member, onOpenChange, onSaved }: { member: Member | null; onOpenChange: (open: boolean) => void; onSaved: () => void }) {
  const [displayName, setDisplayName] = useState("");
  const [tags, setTags] = useState("");
  useEffect(() => {
    setDisplayName(member?.raw_name !== member?.name ? member?.name || "" : "");
    setTags(member?.tags?.join(", ") || "");
  }, [member]);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!member) return;
    await api.updateMemberProfile(member.id, { display_name_override: displayName, tags: tags.split(/[,，]/).map((t) => t.trim()).filter(Boolean) });
    toast.success("成员信息已保存");
    onSaved();
  }
  return (
    <Dialog.Root open={!!member} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content small">
          <Dialog.Title className="dialog-title">编辑成员</Dialog.Title>
          <form className="dialog-body" onSubmit={save}>
            <Field label="飞书原始名称"><input value={member?.raw_name || member?.name || ""} disabled /></Field>
            <Field label="显示名称"><input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="留空则沿用飞书名称" /></Field>
            <Field label="标签"><input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="后端, 负责人, iOS" /></Field>
            <div className="dialog-actions"><Dialog.Close asChild><Button type="button" variant="secondary">取消</Button></Dialog.Close><Button type="submit">保存</Button></div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Button({ children, icon, variant = "primary", size = "md", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { icon?: ReactNode; variant?: "primary" | "secondary" | "danger"; size?: "md" | "sm" }) {
  return <button className={`btn ${variant} ${size}`} {...props}>{icon && <span className="btn-icon">{icon}</span>}{children}</button>;
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (checked: boolean) => void; label: string }) {
  return <label className="toggle-label"><Switch.Root className="switch" checked={checked} onCheckedChange={onChange}><Switch.Thumb className="switch-thumb" /></Switch.Root>{label}</label>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

function Panel({ title, icon, children }: { title: string; icon?: ReactNode; children: ReactNode }) {
  return <section className="panel"><div className="panel-title">{icon && <span>{icon}</span>}{title}</div>{children}</section>;
}

function StatCard({ label, value, helper, icon, tone }: { label: string; value: string; helper: string; icon: ReactNode; tone: string }) {
  return <article className={`stat-card ${tone}`}><div className="stat-icon">{icon}</div><div className="stat-label">{label}</div><div className="stat-value">{value}</div><div className="stat-helper">{helper}</div></article>;
}

function Badge({ children, tone }: { children: ReactNode; tone: "green" | "gray" | "blue" }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

function Avatar({ member }: { member: Member }) {
  const name = member.name || member.display_name || member.id;
  const initials = name.slice(0, 2).toUpperCase();
  return member.avatar ? <img className="avatar" src={member.avatar} alt="" /> : <div className="avatar">{initials}</div>;
}

function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state"><PaperPlaneIcon /><h2>{title}</h2><p>{description}</p>{action}</div>;
}

function Loading() {
  return <div className="loading"><Loader2 className="spin" />加载中</div>;
}

function DataTable({ headers, rows, empty }: { headers: string[]; rows: ReactNode[][]; empty: string }) {
  if (!rows.length) return <div className="empty-line">{empty}</div>;
  return <div className="table-wrap"><table><thead><tr>{headers.map((h) => <th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}</tbody></table></div>;
}

function SunIcon() {
  return <svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="16" fill="#ffd84d" stroke="#152033" strokeWidth="4" /><path d="M32 4v10M32 50v10M4 32h10M50 32h10M12 12l7 7M45 45l7 7M52 12l-7 7M19 45l-7 7" stroke="#152033" strokeWidth="4" strokeLinecap="round" /></svg>;
}

function PaperPlaneIcon() {
  return <svg className="empty-svg" viewBox="0 0 120 92" aria-hidden="true"><path d="M12 44 108 8 78 82 55 56 34 72z" fill="#dff4ff" stroke="#152033" strokeWidth="4" strokeLinejoin="round" /><path d="M55 56 108 8" stroke="#152033" strokeWidth="4" strokeLinecap="round" /><circle cx="24" cy="20" r="9" fill="#ffd84d" stroke="#152033" strokeWidth="4" /><circle cx="94" cy="68" r="7" fill="#62d88f" stroke="#152033" strokeWidth="4" /></svg>;
}

function FloatingDecor() {
  return <svg className="floating-decor" viewBox="0 0 180 180" aria-hidden="true"><rect x="22" y="72" width="62" height="62" rx="8" fill="#ffe9e5" stroke="#152033" strokeWidth="5" transform="rotate(-10 53 103)" /><circle cx="126" cy="54" r="27" fill="#ffd84d" stroke="#152033" strokeWidth="5" /><path d="M104 116c18-17 44-14 55 7-14 15-40 16-55-7Z" fill="#62d88f" stroke="#152033" strokeWidth="5" /></svg>;
}

export default App;

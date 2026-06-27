import * as Dialog from "@radix-ui/react-dialog";
import * as Switch from "@radix-ui/react-switch";
import {
  BarChart3,
  Bot,
  CalendarClock,
  CirclePlus,
  Database,
  Download,
  Edit3,
  Loader2,
  MessageCircle,
  Package,
  RefreshCw,
  Send,
  Settings,
  Sparkles,
  Trash2,
  Users,
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "./lib/api";
import type {
  Channel,
  DataBoard,
  Me,
  Member,
  NavItem,
  ProgressCollection,
  ProgressEntry,
  Project,
  PublishJob,
  SectionId,
  SettingsPayload,
} from "./lib/types";

const primaryNavItems: NavItem[] = [
  { id: "dashboard", label: "数据看板", icon: <BarChart3 /> },
  { id: "collections", label: "收集进度", icon: <MessageCircle /> },
  { id: "publish", label: "定时发布", icon: <Send /> },
];

const secondaryNavItems: NavItem[] = [
  { id: "integrations", label: "集成设置", icon: <Settings /> },
  { id: "skills", label: "Skills", icon: <Package /> },
  { id: "manage", label: "管理页面", icon: <Database /> },
];

const navItems = [...primaryNavItems, ...secondaryNavItems];

const dayOptions = [
  ["mon", "周一"],
  ["tue", "周二"],
  ["wed", "周三"],
  ["thu", "周四"],
  ["fri", "周五"],
  ["sat", "周六"],
  ["sun", "周日"],
];

const defaultReminder = "请按“项目 + 已完成/正在做 + 下一步 + 风险阻塞”的格式提交进度。";

function todayInputDate() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

type CollectionForm = {
  id?: number;
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

type ProgressForm = {
  id?: number;
  user_id: string;
  project_id: string;
  role: string;
  progress_date: string;
  content: string;
};

type ProjectForm = {
  id?: number;
  name: string;
  description: string;
  status: string;
};

type PublishForm = {
  id?: number;
  name: string;
  destination_type: "feishu_channel" | "webhook";
  destination: string;
  schedule_time: string;
  schedule_tz: string;
  schedule_days: string[];
  range_days: number;
  member_ids: string[];
  project_ids: number[];
  ai_summary_enabled: boolean;
  ai_provider: string;
  ai_prompt: string;
  active: boolean;
};

const emptyCollectionForm = (): CollectionForm => ({
  name: "每日进度收集",
  channel_id: "",
  schedule_time: "09:30",
  schedule_tz: "Asia/Shanghai",
  schedule_days: ["mon", "tue", "wed", "thu", "fri"],
  questions: [defaultReminder],
  participants: [],
  reminder_minutes: 0,
  active: true,
});

const emptyProgressForm = (): ProgressForm => ({
  user_id: "",
  project_id: "",
  role: "",
  progress_date: todayInputDate(),
  content: "",
});

const emptyProjectForm = (): ProjectForm => ({
  name: "",
  description: "",
  status: "active",
});

const emptyPublishForm = (): PublishForm => ({
  name: "每日进度快照",
  destination_type: "feishu_channel",
  destination: "",
  schedule_time: "18:00",
  schedule_tz: "Asia/Shanghai",
  schedule_days: ["mon", "tue", "wed", "thu", "fri"],
  range_days: 1,
  member_ids: [],
  project_ids: [],
  ai_summary_enabled: true,
  ai_provider: "deepseek",
  ai_prompt: "",
  active: true,
});

function App() {
  const [section, setSection] = useState<SectionId>("dashboard");
  const [loading, setLoading] = useState(true);
  const [me, setMe] = useState<Me | null>(null);
  const [board, setBoard] = useState<DataBoard | null>(null);
  const [collections, setCollections] = useState<ProgressCollection[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [publishJobs, setPublishJobs] = useState<PublishJob[]>([]);

  const [collectionOpen, setCollectionOpen] = useState(false);
  const [collectionForm, setCollectionForm] = useState<CollectionForm>(emptyCollectionForm);
  const [progressOpen, setProgressOpen] = useState(false);
  const [progressForm, setProgressForm] = useState<ProgressForm>(emptyProgressForm);
  const [progressReloadKey, setProgressReloadKey] = useState(0);
  const [projectOpen, setProjectOpen] = useState(false);
  const [projectForm, setProjectForm] = useState<ProjectForm>(emptyProjectForm);
  const [publishOpen, setPublishOpen] = useState(false);
  const [publishForm, setPublishForm] = useState<PublishForm>(emptyPublishForm);
  const [memberEditor, setMemberEditor] = useState<Member | null>(null);

  useEffect(() => {
    bootstrap();
  }, []);

  async function bootstrap() {
    setLoading(true);
    try {
      const [meRes, boardRes, collectionsRes, membersRes, channelsRes, projectsRes, jobsRes] = await Promise.all([
        api.me(),
        api.dataBoard(),
        api.collections().catch(() => []),
        api.members().catch(() => []),
        api.channels().catch(() => []),
        api.projects().catch(() => []),
        api.publishJobs().catch(() => []),
      ]);
      setMe(meRes);
      setBoard(boardRes);
      setCollections(collectionsRes);
      setMembers(membersRes);
      setChannels(channelsRes);
      setProjects(projectsRes);
      setPublishJobs(jobsRes);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "控制台加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function refreshBoard() {
    setBoard(await api.dataBoard());
  }

  function openCreateCollection() {
    setCollectionForm(emptyCollectionForm());
    setCollectionOpen(true);
  }

  function openEditCollection(item: ProgressCollection) {
    setCollectionForm({
      id: item.id,
      name: item.name,
      channel_id: item.channel_id || "",
      schedule_time: item.schedule_time || "09:30",
      schedule_tz: item.schedule_tz || "Asia/Shanghai",
      schedule_days: item.schedule_days?.length ? item.schedule_days : ["mon", "tue", "wed", "thu", "fri"],
      questions: item.questions?.length ? [item.questions.join("\n")] : [defaultReminder],
      participants: item.participants || [],
      reminder_minutes: item.reminder_minutes || 0,
      active: item.active !== false,
    });
    setCollectionOpen(true);
  }

  async function saveCollection(event: FormEvent) {
    event.preventDefault();
    const reminder = collectionForm.questions.join("\n").trim();
    const payload = { ...collectionForm, questions: reminder ? [reminder] : [defaultReminder] };
    try {
      const saved = collectionForm.id
        ? await api.updateCollection(collectionForm.id, payload)
        : await api.createCollection(payload);
      setCollections((list) => collectionForm.id ? list.map((item) => (item.id === saved.id ? saved : item)) : [...list, saved]);
      setCollectionOpen(false);
      toast.success("收集任务已保存");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  }

  async function deleteCollection(item: ProgressCollection) {
    if (!window.confirm(`确定删除「${item.name}」吗？`)) return;
    await api.deleteCollection(item.id);
    setCollections((list) => list.filter((row) => row.id !== item.id));
  }

  function openCreateProgress() {
    setProgressForm(emptyProgressForm());
    setProgressOpen(true);
  }

  function openEditProgress(entry: ProgressEntry) {
    setProgressForm({
      id: entry.id,
      user_id: entry.user_id,
      project_id: entry.project_id ? String(entry.project_id) : "",
      role: entry.role || "",
      progress_date: entry.progress_date || todayInputDate(),
      content: entry.content || "",
    });
    setProgressOpen(true);
  }

  async function saveProgress(event: FormEvent) {
    event.preventDefault();
    const payload = {
      ...progressForm,
      project_id: progressForm.project_id ? Number(progressForm.project_id) : undefined,
    };
    try {
      if (progressForm.id) await api.updateProgress(progressForm.id, payload);
      else await api.createProgress(payload);
      setProgressOpen(false);
      setProgressReloadKey((value) => value + 1);
      await refreshBoard();
      toast.success("进度记录已保存");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  }

  function openCreateProject() {
    setProjectForm(emptyProjectForm());
    setProjectOpen(true);
  }

  function openEditProject(project: Project) {
    setProjectForm({
      id: project.id,
      name: project.name,
      description: project.description || "",
      status: project.status || "active",
    });
    setProjectOpen(true);
  }

  async function saveProject(event: FormEvent) {
    event.preventDefault();
    try {
      const saved = projectForm.id
        ? await api.updateProject(projectForm.id, projectForm)
        : await api.createProject(projectForm);
      setProjects((list) => projectForm.id ? list.map((item) => (item.id === saved.id ? saved : item)) : [...list, saved]);
      setProjectOpen(false);
      await refreshBoard();
      toast.success("项目已保存");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  }

  function openCreatePublishJob() {
    setPublishForm(emptyPublishForm());
    setPublishOpen(true);
  }

  function openEditPublishJob(job: PublishJob) {
    setPublishForm({
      id: job.id,
      name: job.name,
      destination_type: job.destination_type === "webhook" ? "webhook" : "feishu_channel",
      destination: job.destination || "",
      schedule_time: job.schedule_time || "18:00",
      schedule_tz: job.schedule_tz || "Asia/Shanghai",
      schedule_days: Array.isArray(job.schedule_days) ? job.schedule_days : String(job.schedule_days || "mon,tue,wed,thu,fri").split(","),
      range_days: job.range_days || 1,
      member_ids: job.member_ids || [],
      project_ids: job.project_ids || [],
      ai_summary_enabled: job.ai_summary_enabled !== false,
      ai_provider: job.ai_provider || "deepseek",
      ai_prompt: job.ai_prompt || "",
      active: job.active !== false,
    });
    setPublishOpen(true);
  }

  async function savePublishJob(event: FormEvent) {
    event.preventDefault();
    try {
      const saved = publishForm.id ? await api.updatePublishJob(publishForm.id, publishForm) : await api.createPublishJob(publishForm);
      setPublishJobs((list) => publishForm.id ? list.map((item) => (item.id === saved.id ? saved : item)) : [...list, saved]);
      setPublishOpen(false);
      toast.success("发布任务已保存");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  }

  async function deletePublishJob(job: PublishJob) {
    if (!window.confirm(`确定删除「${job.name}」吗？`)) return;
    await api.deletePublishJob(job.id);
    setPublishJobs((list) => list.filter((item) => item.id !== job.id));
  }

  const currentTitle = navItems.find((item) => item.id === section)?.label || "数据看板";

  return (
    <div className="app-shell">
      <Sidebar section={section} onSelect={setSection} teamName={me?.team_name || "晨序"} />
      <main className="main">
        <Topbar title={currentTitle}>
          {section === "collections" && <Button onClick={openCreateCollection} icon={<CirclePlus />}>新建任务</Button>}
          {section === "publish" && <Button onClick={openCreatePublishJob} icon={<CirclePlus />}>新建发布</Button>}
          {section === "dashboard" && <Button variant="secondary" onClick={refreshBoard} icon={<RefreshCw />}>刷新</Button>}
        </Topbar>
        {loading ? <Loading /> : (
          <>
            {section === "dashboard" && <DataBoardPage board={board} />}
            {section === "collections" && <CollectionsPage collections={collections} channels={channels} members={members} onEdit={openEditCollection} onDelete={deleteCollection} />}
            {section === "publish" && <PublishPage jobs={publishJobs} channels={channels} onEdit={openEditPublishJob} onDelete={deletePublishJob} />}
            {section === "integrations" && <IntegrationsPage channels={channels} members={members} setChannels={setChannels} setMembers={setMembers} />}
            {section === "skills" && <SkillsPage />}
            {section === "manage" && (
              <ManagePage
                members={members}
                projects={projects}
                me={me}
                progressReloadKey={progressReloadKey}
                onCreateProgress={openCreateProgress}
                onEditProgress={openEditProgress}
                onEditMember={setMemberEditor}
                onRefreshMembers={async () => setMembers(await api.members())}
                onCreateProject={openCreateProject}
                onEditProject={openEditProject}
              />
            )}
          </>
        )}
      </main>
      <CollectionDialog open={collectionOpen} onOpenChange={setCollectionOpen} form={collectionForm} setForm={setCollectionForm} channels={channels} members={members} onSubmit={saveCollection} />
      <ProgressDialog open={progressOpen} onOpenChange={setProgressOpen} form={progressForm} setForm={setProgressForm} members={members} projects={projects} onSubmit={saveProgress} />
      <ProjectDialog open={projectOpen} onOpenChange={setProjectOpen} form={projectForm} setForm={setProjectForm} onSubmit={saveProject} />
      <PublishDialog open={publishOpen} onOpenChange={setPublishOpen} form={publishForm} setForm={setPublishForm} channels={channels} members={members} projects={projects} onSubmit={savePublishJob} />
      <MemberDialog member={memberEditor} onOpenChange={(open) => !open && setMemberEditor(null)} onSaved={async () => { setMemberEditor(null); setMembers(await api.members()); }} />
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
          <div className="brand-subtitle">进度中枢</div>
        </div>
      </div>
      <nav className="nav-list main-nav">
        {primaryNavItems.map((item) => (
          <button key={item.id} className={`nav-button ${section === item.id ? "active" : ""}`} onClick={() => onSelect(item.id)}>
            <span className="nav-icon">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <nav className="nav-list secondary-nav">
        {secondaryNavItems.map((item) => (
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

function Topbar({ title, children }: { title: string; children?: ReactNode }) {
  return <header className="topbar"><h1>{title}</h1><div className="topbar-actions">{children}</div></header>;
}

function DataBoardPage({ board }: { board: DataBoard | null }) {
  const data = board || { total_entries: 0, active_members: 0, active_projects: 0, updated_today: 0, by_project: [], by_member: [], by_date: [], recent_entries: [] };
  return (
    <section className="content-stack">
      <div className="stats-grid">
        <StatCard tone="yellow" label="进度记录" value={String(data.total_entries)} helper="最近 7 天" icon={<Database />} />
        <StatCard tone="mint" label="成员" value={String(data.active_members)} helper="当前活跃" icon={<Users />} />
        <StatCard tone="blue" label="项目" value={String(data.active_projects)} helper="进行中" icon={<Sparkles />} />
        <StatCard tone="red" label="今日更新" value={String(data.updated_today)} helper="已确认入库" icon={<CalendarClock />} />
      </div>
      <div className="two-column">
        <Panel title="项目维度"><BarList rows={data.by_project} empty="暂无项目数据" /></Panel>
        <Panel title="成员维度"><BarList rows={data.by_member} empty="暂无成员数据" /></Panel>
      </div>
      <Panel title="最近进度">
        <ProgressRows entries={data.recent_entries} />
      </Panel>
    </section>
  );
}

function CollectionsPage({ collections, channels, members, onEdit, onDelete }: { collections: ProgressCollection[]; channels: Channel[]; members: Member[]; onEdit: (item: ProgressCollection) => void; onDelete: (item: ProgressCollection) => void }) {
  const channelName = (id: string) => channels.find((c) => c.id === id)?.name || id || "未设置";
  return (
    <section className="content-stack">
      {collections.length ? collections.map((item) => (
        <article className="task-row" key={item.id}>
          <div className="row-icon"><MessageCircle /></div>
          <div className="row-main">
            <div className="row-title">{item.name}</div>
            <div className="row-meta">
              <span>{item.schedule_time}</span>
              <span>{item.schedule_days.map((d) => dayOptions.find(([id]) => id === d)?.[1] || d).join("、")}</span>
              <span>{item.participants.length || members.length} 人</span>
              <span>#{channelName(item.channel_id)}</span>
            </div>
          </div>
          <Badge tone={item.active ? "green" : "gray"}>{item.active ? "启用" : "暂停"}</Badge>
          <Button size="sm" variant="secondary" onClick={() => onEdit(item)} icon={<Edit3 />}>编辑</Button>
          <Button size="sm" variant="danger" onClick={() => onDelete(item)} icon={<Trash2 />}>删除</Button>
        </article>
      )) : <EmptyState title="没有收集任务" action={null} />}
    </section>
  );
}

function ManagePage({
  members,
  projects,
  me,
  progressReloadKey,
  onCreateProgress,
  onEditProgress,
  onEditMember,
  onRefreshMembers,
  onCreateProject,
  onEditProject,
}: {
  members: Member[];
  projects: Project[];
  me: Me | null;
  progressReloadKey: number;
  onCreateProgress: () => void;
  onEditProgress: (entry: ProgressEntry) => void;
  onEditMember: (member: Member) => void;
  onRefreshMembers: () => Promise<void>;
  onCreateProject: () => void;
  onEditProject: (project: Project) => void;
}) {
  const [tab, setTab] = useState<"records" | "members" | "projects">("records");
  return (
    <section className="content-stack">
      <div className="tabs">
        <button className={tab === "records" ? "active" : ""} onClick={() => setTab("records")}>记录</button>
        <button className={tab === "members" ? "active" : ""} onClick={() => setTab("members")}>成员</button>
        <button className={tab === "projects" ? "active" : ""} onClick={() => setTab("projects")}>项目</button>
      </div>
      {tab === "records" && <ProgressPage members={members} projects={projects} reloadKey={progressReloadKey} onCreate={onCreateProgress} onEdit={onEditProgress} />}
      {tab === "members" && <MembersPage members={members} me={me} onEdit={onEditMember} onRefresh={onRefreshMembers} />}
      {tab === "projects" && <ProjectsPage projects={projects} onCreate={onCreateProject} onEdit={onEditProject} />}
    </section>
  );
}

function ProgressPage({ members, projects, reloadKey, onCreate, onEdit }: { members: Member[]; projects: Project[]; reloadKey: number; onCreate: () => void; onEdit: (entry: ProgressEntry) => void }) {
  const [entries, setEntries] = useState<ProgressEntry[]>([]);
  const [memberId, setMemberId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  useEffect(() => { load(); }, [memberId, projectId, dateFrom, dateTo, reloadKey]);
  async function load() {
    const params = new URLSearchParams();
    if (memberId) params.set("user_id", memberId);
    if (projectId) params.set("project_id", projectId);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    setEntries(await api.progress(params));
  }
  return (
    <section className="content-stack">
      <div className="filter-bar">
        <label><span>成员</span><select value={memberId} onChange={(e) => setMemberId(e.target.value)}><option value="">全部成员</option>{members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
        <label><span>项目</span><select value={projectId} onChange={(e) => setProjectId(e.target.value)}><option value="">全部项目</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label><span>开始日期</span><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label>
        <label><span>结束日期</span><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label>
        <Button onClick={onCreate} icon={<CirclePlus />}>新建记录</Button>
      </div>
      <Panel title="进度记录">
        <ProgressRows entries={entries} onEdit={onEdit} />
      </Panel>
    </section>
  );
}

function MembersPage({ members, me, onEdit, onRefresh }: { members: Member[]; me: Me | null; onEdit: (m: Member) => void; onRefresh: () => Promise<void> }) {
  return (
    <section className="content-stack">
      <div className="actions"><Button variant="secondary" onClick={onRefresh} icon={<RefreshCw />}>同步成员</Button></div>
      <div className="members-grid">
        {members.map((member) => (
          <article className="member-card" key={member.id}>
            <Avatar member={member} />
            <div className="member-body">
              <div className="member-name">{member.name || member.id}</div>
              <div className="member-raw">{member.raw_name || member.email || member.id}</div>
              {!!member.tags?.length && <div className="tag-row">{member.tags.map((tag) => <span key={tag} className="tag">{tag}</span>)}</div>}
              {me?.role === "admin" && <button className="text-button" onClick={() => onEdit(member)}>编辑</button>}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function ProjectsPage({ projects, onCreate, onEdit }: { projects: Project[]; onCreate: () => void; onEdit: (project: Project) => void }) {
  return (
    <Panel title="项目信息">
      <div className="actions pad-bottom"><Button onClick={onCreate} icon={<CirclePlus />}>新建项目</Button></div>
      <DataTable
        headers={["项目", "状态", "描述", ""]}
        rows={projects.map((project) => [
          project.name,
          project.status || "active",
          project.description || "",
          <Button key={project.id} size="sm" variant="secondary" onClick={() => onEdit(project)} icon={<Edit3 />}>编辑</Button>,
        ])}
        empty="暂无项目"
      />
    </Panel>
  );
}

function PublishPage({ jobs, channels, onEdit, onDelete }: { jobs: PublishJob[]; channels: Channel[]; onEdit: (job: PublishJob) => void; onDelete: (job: PublishJob) => void }) {
  const channelName = (id: string) => channels.find((c) => c.id === id)?.name || id;
  return (
    <section className="content-stack">
      {jobs.length ? jobs.map((job) => (
        <article className="task-row" key={job.id}>
          <div className="row-icon"><Send /></div>
          <div className="row-main">
            <div className="row-title">{job.name}</div>
            <div className="row-meta">
              <span>{job.schedule_time}</span>
              <span>{job.destination_type === "webhook" ? "Webhook" : `#${channelName(job.destination)}`}</span>
              <span>最近 {job.range_days} 天</span>
              <span>{job.ai_summary_enabled ? "AI 摘要" : "无 AI"}</span>
            </div>
          </div>
          <Badge tone={job.active ? "green" : "gray"}>{job.active ? "启用" : "暂停"}</Badge>
          <Button size="sm" variant="secondary" onClick={() => onEdit(job)} icon={<Edit3 />}>编辑</Button>
          <Button size="sm" variant="danger" onClick={() => onDelete(job)} icon={<Trash2 />}>删除</Button>
        </article>
      )) : <EmptyState title="没有发布任务" action={null} />}
    </section>
  );
}

function IntegrationsPage({ channels, members, setChannels, setMembers }: { channels: Channel[]; members: Member[]; setChannels: (items: Channel[]) => void; setMembers: (items: Member[]) => void }) {
  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  useEffect(() => { api.settings().then((payload) => { setSettings(payload); setValues(payload.values || {}); }); }, []);
  function set(key: string, value: string) { setValues((old) => ({ ...old, [key]: value })); }
  async function save(show = true) {
    const payload = await api.saveSettings(values);
    setSettings(payload);
    setValues(payload.values || {});
    if (show) toast.success("设置已保存");
  }
  async function connect() {
    await save(false);
    const nextChannels = await api.channels();
    setChannels(nextChannels);
    if (nextChannels[0]) setMembers(await api.members(nextChannels[0].id));
    toast.success("飞书已连接");
  }
  const secret = settings?.secret_set || {};
  return (
    <section className="settings-layout">
      <Panel title="飞书" icon={<Bot />}>
        <div className="form-grid">
          <Field label="事件接收"><select value={values.FEISHU_EVENT_MODE || "ws"} onChange={(e) => set("FEISHU_EVENT_MODE", e.target.value)}><option value="ws">长连接</option><option value="webhook">公网回调</option></select></Field>
          <Field label="App ID"><input value={values.FEISHU_APP_ID || ""} onChange={(e) => set("FEISHU_APP_ID", e.target.value)} /></Field>
          <Field label="App Secret"><input type="password" value={values.FEISHU_APP_SECRET || ""} onChange={(e) => set("FEISHU_APP_SECRET", e.target.value)} placeholder={secret.FEISHU_APP_SECRET ? "已配置，留空不变" : "未配置"} /></Field>
          <Field label="默认群聊"><select value={values.FEISHU_DEFAULT_CHAT_ID || ""} onChange={(e) => set("FEISHU_DEFAULT_CHAT_ID", e.target.value)}><option value="">选择群聊</option>{channels.map((c) => <option key={c.id} value={c.id}>#{c.name}</option>)}</select></Field>
          <Field label="管理员"><select value={values.FEISHU_ADMIN_OPEN_ID || ""} onChange={(e) => set("FEISHU_ADMIN_OPEN_ID", e.target.value)}><option value="">选择管理员</option>{members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></Field>
        </div>
        <div className="actions"><Button onClick={connect} icon={<RefreshCw />}>连接飞书</Button><Button variant="secondary" onClick={() => save()}>保存</Button></div>
      </Panel>
      <Panel title="AI" icon={<Sparkles />}>
        <div className="form-grid">
          <Field label="默认服务"><select value={values.FEISHU_AI_PROVIDER || "deepseek"} onChange={(e) => set("FEISHU_AI_PROVIDER", e.target.value)}><option value="deepseek">DeepSeek</option><option value="openai">OpenAI</option></select></Field>
          <Field label="OpenAI Key"><input type="password" value={values.OPENAI_API_KEY || ""} onChange={(e) => set("OPENAI_API_KEY", e.target.value)} placeholder={secret.OPENAI_API_KEY ? "已配置，留空不变" : "未配置"} /></Field>
          <Field label="DeepSeek Key"><input type="password" value={values.DEEPSEEK_API_KEY || ""} onChange={(e) => set("DEEPSEEK_API_KEY", e.target.value)} placeholder={secret.DEEPSEEK_API_KEY ? "已配置，留空不变" : "未配置"} /></Field>
          <Field label="DeepSeek Base URL"><input value={values.DEEPSEEK_BASE_URL || "https://api.deepseek.com"} onChange={(e) => set("DEEPSEEK_BASE_URL", e.target.value)} /></Field>
          <Field label="DeepSeek 模型"><input value={values.DEEPSEEK_MODEL || "deepseek-chat"} onChange={(e) => set("DEEPSEEK_MODEL", e.target.value)} /></Field>
        </div>
        <div className="actions"><Button onClick={() => save()}>保存</Button></div>
      </Panel>
    </section>
  );
}

function SkillsPage() {
  const [pkg, setPkg] = useState<{ version: string; filename: string; download_url: string } | null>(null);
  useEffect(() => { api.skillsPackage().then(setPkg); }, []);
  return (
    <section className="content-stack">
      <Panel title="Skills 包" icon={<Package />}>
        <div className="download-card">
          <div>
            <div className="download-title">{pkg?.filename || "chenxu-skills.zip"}</div>
            <div className="download-meta">版本 {pkg?.version || "-"}</div>
          </div>
          <a className="btn primary" href={pkg?.download_url || "/dashboard/api/skills-package/download"}>
            <span className="btn-icon"><Download /></span>
            下载
          </a>
        </div>
      </Panel>
    </section>
  );
}

function CollectionDialog({ open, onOpenChange, form, setForm, channels, members, onSubmit }: { open: boolean; onOpenChange: (open: boolean) => void; form: CollectionForm; setForm: (updater: CollectionForm | ((old: CollectionForm) => CollectionForm)) => void; channels: Channel[]; members: Member[]; onSubmit: (event: FormEvent) => void }) {
  function set<K extends keyof CollectionForm>(key: K, value: CollectionForm[K]) { setForm((old) => ({ ...old, [key]: value })); }
  function toggleDay(day: string) { set("schedule_days", form.schedule_days.includes(day) ? form.schedule_days.filter((d) => d !== day) : [...form.schedule_days, day]); }
  function toggleMember(id: string) { set("participants", form.participants.includes(id) ? form.participants.filter((item) => item !== id) : [...form.participants, id]); }
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog-content">
        <Dialog.Title className="dialog-title">{form.id ? "编辑收集任务" : "新建收集任务"}</Dialog.Title>
        <form className="dialog-body" onSubmit={onSubmit}>
          <div className="form-grid">
            <Field label="名称"><input value={form.name} onChange={(e) => set("name", e.target.value)} required /></Field>
            <Field label="提醒群"><select value={form.channel_id} onChange={(e) => set("channel_id", e.target.value)}><option value="">不指定</option>{channels.map((c) => <option key={c.id} value={c.id}>#{c.name}</option>)}</select></Field>
            <Field label="时间"><input type="time" value={form.schedule_time} onChange={(e) => set("schedule_time", e.target.value)} /></Field>
            <Field label="时区"><input value={form.schedule_tz} onChange={(e) => set("schedule_tz", e.target.value)} /></Field>
          </div>
          <Field label="工作日"><div className="chip-row">{dayOptions.map(([id, label]) => <button type="button" key={id} className={`chip ${form.schedule_days.includes(id) ? "active" : ""}`} onClick={() => toggleDay(id)}>{label}</button>)}</div></Field>
          <Field label="参与成员"><div className="participant-grid">{members.map((m) => <button type="button" key={m.id} className={`participant ${form.participants.includes(m.id) ? "active" : ""}`} onClick={() => toggleMember(m.id)}>{m.name}</button>)}</div></Field>
          <Field label="提醒内容"><textarea value={form.questions.join("\n")} onChange={(e) => set("questions", [e.target.value])} required /></Field>
          <div className="switch-row"><Toggle checked={form.active} onChange={(value) => set("active", value)} label="启用" /></div>
          <DialogActions />
        </form>
      </Dialog.Content></Dialog.Portal>
    </Dialog.Root>
  );
}

function ProgressDialog({ open, onOpenChange, form, setForm, members, projects, onSubmit }: { open: boolean; onOpenChange: (open: boolean) => void; form: ProgressForm; setForm: (updater: ProgressForm | ((old: ProgressForm) => ProgressForm)) => void; members: Member[]; projects: Project[]; onSubmit: (event: FormEvent) => void }) {
  function set<K extends keyof ProgressForm>(key: K, value: ProgressForm[K]) { setForm((old) => ({ ...old, [key]: value })); }
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog-content">
        <Dialog.Title className="dialog-title">{form.id ? "编辑进度记录" : "新建进度记录"}</Dialog.Title>
        <form className="dialog-body" onSubmit={onSubmit}>
          <div className="form-grid">
            <Field label="成员"><select value={form.user_id} onChange={(e) => set("user_id", e.target.value)} required><option value="">选择成员</option>{members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></Field>
            <Field label="项目"><select value={form.project_id} onChange={(e) => set("project_id", e.target.value)}><option value="">未归属项目</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
            <Field label="岗位"><input value={form.role} onChange={(e) => set("role", e.target.value)} /></Field>
            <Field label="日期"><input type="date" value={form.progress_date} onChange={(e) => set("progress_date", e.target.value)} required /></Field>
          </div>
          <Field label="进度内容"><textarea value={form.content} onChange={(e) => set("content", e.target.value)} required /></Field>
          <DialogActions />
        </form>
      </Dialog.Content></Dialog.Portal>
    </Dialog.Root>
  );
}

function ProjectDialog({ open, onOpenChange, form, setForm, onSubmit }: { open: boolean; onOpenChange: (open: boolean) => void; form: ProjectForm; setForm: (updater: ProjectForm | ((old: ProjectForm) => ProjectForm)) => void; onSubmit: (event: FormEvent) => void }) {
  function set<K extends keyof ProjectForm>(key: K, value: ProjectForm[K]) { setForm((old) => ({ ...old, [key]: value })); }
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog-content small">
        <Dialog.Title className="dialog-title">{form.id ? "编辑项目" : "新建项目"}</Dialog.Title>
        <form className="dialog-body" onSubmit={onSubmit}>
          <Field label="项目名称"><input value={form.name} onChange={(e) => set("name", e.target.value)} required /></Field>
          <Field label="状态"><select value={form.status} onChange={(e) => set("status", e.target.value)}><option value="active">进行中</option><option value="paused">暂停</option><option value="done">已完成</option></select></Field>
          <Field label="描述"><textarea value={form.description} onChange={(e) => set("description", e.target.value)} /></Field>
          <DialogActions />
        </form>
      </Dialog.Content></Dialog.Portal>
    </Dialog.Root>
  );
}

function PublishDialog({ open, onOpenChange, form, setForm, channels, members, projects, onSubmit }: { open: boolean; onOpenChange: (open: boolean) => void; form: PublishForm; setForm: (updater: PublishForm | ((old: PublishForm) => PublishForm)) => void; channels: Channel[]; members: Member[]; projects: Project[]; onSubmit: (event: FormEvent) => void }) {
  function set<K extends keyof PublishForm>(key: K, value: PublishForm[K]) { setForm((old) => ({ ...old, [key]: value })); }
  function toggleDay(day: string) { set("schedule_days", form.schedule_days.includes(day) ? form.schedule_days.filter((d) => d !== day) : [...form.schedule_days, day]); }
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog-content">
        <Dialog.Title className="dialog-title">{form.id ? "编辑发布任务" : "新建发布任务"}</Dialog.Title>
        <form className="dialog-body" onSubmit={onSubmit}>
          <div className="form-grid">
            <Field label="名称"><input value={form.name} onChange={(e) => set("name", e.target.value)} required /></Field>
            <Field label="目标类型"><select value={form.destination_type} onChange={(e) => set("destination_type", e.target.value as PublishForm["destination_type"])}><option value="feishu_channel">飞书群</option><option value="webhook">Webhook</option></select></Field>
            <Field label="目标">{form.destination_type === "feishu_channel" ? <select value={form.destination} onChange={(e) => set("destination", e.target.value)}><option value="">选择群聊</option>{channels.map((c) => <option key={c.id} value={c.id}>#{c.name}</option>)}</select> : <input value={form.destination} onChange={(e) => set("destination", e.target.value)} />}</Field>
            <Field label="时间"><input type="time" value={form.schedule_time} onChange={(e) => set("schedule_time", e.target.value)} /></Field>
            <Field label="范围天数"><input type="number" min={1} value={form.range_days} onChange={(e) => set("range_days", Number(e.target.value))} /></Field>
            <Field label="AI 服务"><select value={form.ai_provider} onChange={(e) => set("ai_provider", e.target.value)}><option value="deepseek">DeepSeek</option><option value="openai">OpenAI</option></select></Field>
          </div>
          <Field label="工作日"><div className="chip-row">{dayOptions.map(([id, label]) => <button type="button" key={id} className={`chip ${form.schedule_days.includes(id) ? "active" : ""}`} onClick={() => toggleDay(id)}>{label}</button>)}</div></Field>
          <Field label="成员范围"><div className="participant-grid">{members.map((m) => <button type="button" key={m.id} className={`participant ${form.member_ids.includes(m.id) ? "active" : ""}`} onClick={() => set("member_ids", form.member_ids.includes(m.id) ? form.member_ids.filter((id) => id !== m.id) : [...form.member_ids, m.id])}>{m.name}</button>)}</div></Field>
          <Field label="项目范围"><div className="participant-grid">{projects.map((p) => <button type="button" key={p.id} className={`participant ${form.project_ids.includes(p.id) ? "active" : ""}`} onClick={() => set("project_ids", form.project_ids.includes(p.id) ? form.project_ids.filter((id) => id !== p.id) : [...form.project_ids, p.id])}>{p.name}</button>)}</div></Field>
          <Field label="摘要提示词"><textarea value={form.ai_prompt} onChange={(e) => set("ai_prompt", e.target.value)} /></Field>
          <div className="switch-row"><Toggle checked={form.ai_summary_enabled} onChange={(value) => set("ai_summary_enabled", value)} label="AI 摘要" /><Toggle checked={form.active} onChange={(value) => set("active", value)} label="启用" /></div>
          <DialogActions />
        </form>
      </Dialog.Content></Dialog.Portal>
    </Dialog.Root>
  );
}

function MemberDialog({ member, onOpenChange, onSaved }: { member: Member | null; onOpenChange: (open: boolean) => void; onSaved: () => void }) {
  const [displayName, setDisplayName] = useState("");
  const [tags, setTags] = useState("");
  useEffect(() => { setDisplayName(member?.raw_name !== member?.name ? member?.name || "" : ""); setTags(member?.tags?.join(", ") || ""); }, [member]);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!member) return;
    await api.updateMemberProfile(member.id, { display_name_override: displayName, tags: tags.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean) });
    toast.success("成员已保存");
    onSaved();
  }
  return (
    <Dialog.Root open={!!member} onOpenChange={onOpenChange}>
      <Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog-content small">
        <Dialog.Title className="dialog-title">编辑成员</Dialog.Title>
        <form className="dialog-body" onSubmit={save}>
          <Field label="飞书名称"><input value={member?.raw_name || member?.name || ""} disabled /></Field>
          <Field label="显示名称"><input value={displayName} onChange={(e) => setDisplayName(e.target.value)} /></Field>
          <Field label="岗位/标签"><input value={tags} onChange={(e) => setTags(e.target.value)} /></Field>
          <DialogActions />
        </form>
      </Dialog.Content></Dialog.Portal>
    </Dialog.Root>
  );
}

function ProgressRows({ entries, onEdit, editLabel = "编辑" }: { entries: ProgressEntry[]; onEdit?: (entry: ProgressEntry) => void; editLabel?: string }) {
  if (!entries.length) return <div className="empty-line">暂无数据</div>;
  return (
    <div className="report-list">
      {entries.map((entry) => (
        <article className="report-row" key={entry.id}>
          <div className="report-person">{entry.member_name || entry.user_id}</div>
          <div className="report-copy">
            <strong>{entry.project_name || "未归属项目"}</strong>
            <div>{entry.content}</div>
          </div>
          {onEdit && <Button size="sm" variant="secondary" onClick={() => onEdit(entry)}>{editLabel}</Button>}
        </article>
      ))}
    </div>
  );
}

function BarList({ rows, empty }: { rows: Array<{ name: string; count: number }>; empty: string }) {
  const max = Math.max(1, ...rows.map((row) => row.count));
  if (!rows.length) return <div className="empty-line">{empty}</div>;
  return <div className="bar-list">{rows.map((row) => <div className="bar-row" key={row.name}><span>{row.name}</span><div><i style={{ width: `${Math.max(8, row.count / max * 100)}%` }} /></div><b>{row.count}</b></div>)}</div>;
}

function DialogActions() {
  return <div className="dialog-actions"><Dialog.Close asChild><Button type="button" variant="secondary">取消</Button></Dialog.Close><Button type="submit">保存</Button></div>;
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
  return member.avatar ? <img className="avatar" src={member.avatar} alt="" /> : <div className="avatar">{name.slice(0, 2).toUpperCase()}</div>;
}

function EmptyState({ title, action }: { title: string; action?: ReactNode }) {
  return <div className="empty-state"><PaperPlaneIcon /><h2>{title}</h2>{action}</div>;
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

export default App;

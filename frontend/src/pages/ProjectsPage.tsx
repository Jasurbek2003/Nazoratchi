import { memo, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useProbes, useProjects } from "../api/queries";
import type { Probe, Project } from "../api/types";
import { usePageTitle } from "../app/context";
import { EmptyState, ErrorState, SkeletonRows } from "../components/Feedback";
import { StatusBadge, STATUS_CLASS } from "../components/Status";
import { filterProjects } from "../lib/filters";
import { KIND_LABEL, projectHealth } from "../lib/projectStatus";
import { useNow } from "../lib/useNow";

const PAGE = 25;

export function ProjectBadges({ project }: { project: Project }) {
  return (
    <>
      {!project.moved && (
        <span className="inline-flex items-center rounded-full border border-dashed border-warning bg-warning-bg px-2 py-0.5 text-xs font-medium text-warning-fg" title="Loyiha hali yangi serverga ko'chirilmagan">
          Ko&apos;chirilmagan
        </span>
      )}
      {project.status === "archived" && (
        <span className="inline-flex items-center rounded-full border border-dashed border-unknown bg-unknown-bg px-2 py-0.5 text-xs font-medium text-unknown-fg">Arxiv</span>
      )}
    </>
  );
}

const ProjectRow = memo(function ProjectRow({ project, probes, now }: { project: Project; probes: Probe[]; now: number }) {
  const health = projectHealth(project, probes, now);
  return (
    <li className="panel relative grid grid-cols-2 items-start gap-x-4 gap-y-2 py-3 pl-4 pr-3 hover:bg-surface-2 md:grid-cols-[minmax(180px,1.4fr)_110px_minmax(160px,1.4fr)_minmax(160px,1.4fr)_minmax(140px,1fr)]">
      <span className={`absolute inset-y-0 left-0 w-1 rounded-l-[10px] ${STATUS_CLASS[health.status].bar}`} aria-hidden />
      <div className="col-span-2 min-w-0 md:col-span-1">
        <Link to={`/projects/${project.id}`} className="font-semibold after:absolute after:inset-0 after:content-['']">
          {project.name}
        </Link>
        <p className="mono text-muted">{project.slug}</p>
        <div className="mt-1 flex flex-wrap gap-1">
          <ProjectBadges project={project} />
        </div>
      </div>
      <div className="text-[13px]">
        <span className="text-xs text-muted md:sr-only">Tur: </span>
        {KIND_LABEL[project.kind]}
      </div>
      <div className="col-span-2 text-[13px] md:col-span-1">
        <p className="text-xs text-muted md:sr-only">Serverlar</p>
        {project.servers_info.length === 0 ? (
          <span className="text-muted">server biriktirilmagan</span>
        ) : (
          <ul className="m-0 list-none space-y-0.5 p-0">
            {project.servers_info.map((s) => (
              <li key={`${s.server_id}-${s.environment}`}>
                <span className="font-medium">{s.server}</span>
                {s.environment !== "production" && <span className="text-muted"> ({s.environment})</span>}
                {s.ports.length > 0 && <span className="mono text-muted"> :{s.ports.join(", :")}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="col-span-2 min-w-0 text-[13px] md:col-span-1">
        <p className="text-xs text-muted md:sr-only">Domenlar</p>
        {project.domains_info.length === 0 ? (
          <span className="text-muted">domen yo&apos;q</span>
        ) : (
          <ul className="m-0 list-none space-y-0.5 p-0">
            {project.domains_info.slice(0, 3).map((d) => (
              <li key={d.id} className="mono truncate">
                {d.fqdn}
              </li>
            ))}
            {project.domains_info.length > 3 && <li className="text-muted">yana {project.domains_info.length - 3} ta</li>}
          </ul>
        )}
      </div>
      <div className="col-span-2 md:col-span-1">
        <StatusBadge status={health.status} label={health.label} size="sm" />
        {health.total > 0 && <p className="mt-1 text-xs text-muted num">{health.total} ta tekshiruv</p>}
      </div>
    </li>
  );
});

export default function ProjectsPage() {
  usePageTitle("Loyihalar");
  const now = Math.floor(useNow() / 15_000) * 15_000; // satrlar har soniyada emas, 15 soniyada qayta chiziladi
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const scope = params.get("scope") === "archived" ? "archived" : "active";
  const projects = useProjects(scope);
  const probes = useProbes();
  const [limit, setLimit] = useState(PAGE);

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
    setLimit(PAGE);
  };

  const visible = useMemo(() => filterProjects(projects.data ?? [], { q }), [projects.data, q]);
  const shown = visible.slice(0, limit);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Loyihalar</h1>
        <p className="text-muted num" aria-live="polite">
          {projects.data ? `${visible.length} / ${projects.data.length} loyiha` : ""}
        </p>
      </div>

      <form role="search" aria-label="Loyihalarni filtrlash" className="grid gap-2 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto]" onSubmit={(e) => e.preventDefault()}>
        <div>
          <label htmlFor="prj-q" className="sr-only">
            Qidirish
          </label>
          <input id="prj-q" type="search" className="field" placeholder="Nom, slug, domen yoki server bo'yicha qidirish" value={q} onChange={(e) => set("q", e.target.value)} />
        </div>
        <div>
          <label htmlFor="prj-scope" className="sr-only">
            Holat
          </label>
          <select id="prj-scope" className="field" value={scope} onChange={(e) => set("scope", e.target.value === "archived" ? "archived" : "")}>
            <option value="active">Faol loyihalar</option>
            <option value="archived">Arxivdagilar</option>
          </select>
        </div>
        <button type="button" className="btn" disabled={!q && scope === "active"} onClick={() => setParams({}, { replace: true })}>
          Tozalash
        </button>
      </form>

      {probes.error && !probes.data && (
        <p role="status" className="rounded bg-warning-bg px-3 py-2 text-warning-fg">
          Tekshiruvlar yuklanmadi: loyiha holati &quot;noma&apos;lum&quot; deb ko&apos;rsatiladi.
        </p>
      )}

      {projects.isPending ? (
        <SkeletonRows rows={6} className="h-[84px]" />
      ) : projects.error && !projects.data ? (
        <ErrorState error={projects.error} onRetry={() => void projects.refetch()} title="Loyihalarni yuklab bo'lmadi" />
      ) : projects.data!.length === 0 ? (
        <EmptyState title={scope === "archived" ? "Arxivda loyiha yo'q" : "Hali loyiha qo'shilmagan"} hint="Loyihalar reyestri shu yerda ko'rinadi." />
      ) : visible.length === 0 ? (
        <EmptyState
          title="Hech narsa topilmadi"
          hint="Qidiruv shartiga mos loyiha yo'q."
          action={
            <button type="button" className="btn" onClick={() => setParams({}, { replace: true })}>
              Filtrni tozalash
            </button>
          }
        />
      ) : (
        <>
          <ul className="m-0 list-none space-y-2 p-0">
            {shown.map((p) => (
              <ProjectRow key={p.id} project={p} probes={probes.data ?? EMPTY} now={now} />
            ))}
          </ul>
          {visible.length > shown.length && (
            <div className="text-center">
              <button type="button" className="btn" onClick={() => setLimit((l) => l + PAGE)}>
                Yana {Math.min(PAGE, visible.length - shown.length)} ta ko&apos;rsatish
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

const EMPTY: Probe[] = [];

import Link from "next/link";
import {
  Activity,
  ArrowDownToLine,
  Database,
  FileText,
  Globe2,
  LayoutDashboard,
  RadioTower,
  Rocket,
  Settings,
  Timer,
  Workflow,
} from "lucide-react";

export function short(value: unknown, max = 72) {
  const text = value === null || value === undefined || value === "" ? "-" : String(value);
  return text.length > max ? `${text.slice(0, max - 1)}...` : text;
}

export function Status({ value }: { value: unknown }) {
  return <span className="status">{short(value, 28)}</span>;
}

export function listValue(value: unknown, maxItems = 3) {
  const items = Array.isArray(value) ? value : [];
  if (!items.length) return "-";
  return items.slice(0, maxItems).map((item) => short(item, 36)).join(", ");
}

export function Metric({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number;
  icon: typeof Database;
}) {
  return (
    <div className="metric">
      <div className="metricIcon">
        <Icon size={18} />
      </div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div>
        <div className="brand">
          <div className="brandMark">CP</div>
          <div>
            <strong>ContentPilot</strong>
            <span>Resource Operations</span>
          </div>
        </div>
        <nav>
          <Link href="/"><LayoutDashboard size={16} /> Dashboard</Link>
          <Link href="/sites"><Globe2 size={16} /> Sites</Link>
          <Link href="/queue"><RadioTower size={16} /> URL Queue</Link>
          <Link href="/pages"><FileText size={16} /> Pages</Link>
          <Link href="/pipeline"><Rocket size={16} /> Pipeline</Link>
          <Link href="/tasks"><Timer size={16} /> Tasks</Link>
          <Link href="/templates"><Workflow size={16} /> Templates</Link>
        </nav>
      </div>
      <Link className="settingsLink" href="/settings"><Settings size={16} /> Settings</Link>
    </aside>
  );
}

export const metricIcons = {
  sites: Globe2,
  queuedUrls: RadioTower,
  pages: FileText,
  embeddings: Database,
  vectors: Activity,
  topics: ArrowDownToLine,
  contentItems: Rocket,
  publications: Rocket,
};

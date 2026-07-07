import { ExternalLink, Play } from "lucide-react";
import { runTask } from "@/lib/actions";
import { getDashboardData } from "@/lib/data";
import { Metric, Status, metricIcons, short } from "./_components";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const data = await getDashboardData();
  const n8nUrl = process.env.N8N_WEB_URL?.trim();

  return (
    <>
      <header className="topbar">
        <div>
          <p className="eyebrow">Postgres + pgvector</p>
          <h1>Dashboard</h1>
          <p>Operational cockpit for acquisition volume, crawl health, indexed resources, and publishing progress.</p>
        </div>
        <div className="topbarActions">
          {n8nUrl ? (
            <a className="iconButton" href={n8nUrl} target="_blank" rel="noreferrer">
              <ExternalLink size={16} /> n8n
            </a>
          ) : null}
          <form action={runTask} className="quickRun">
            <input name="base_url" placeholder="https://example.com" />
            <input name="discover_limit" type="number" min="1" defaultValue="200" aria-label="Discover limit" />
            <input name="process_limit" type="number" min="1" defaultValue="20" aria-label="Process limit" />
            <button name="task" value="crawl-run">
              <Play size={16} /> Run
            </button>
          </form>
        </div>
      </header>

      <section className="metricGrid">
        <Metric label="Sites" value={data.metrics.sites} icon={metricIcons.sites} />
        <Metric label="Queued URLs" value={data.metrics.queuedUrls} icon={metricIcons.queuedUrls} />
        <Metric label="Pages" value={data.metrics.pages} icon={metricIcons.pages} />
        <Metric label="Embeddings" value={data.metrics.embeddings} icon={metricIcons.embeddings} />
        <Metric label="Vectors" value={data.metrics.vectors} icon={metricIcons.vectors} />
        <Metric label="Topics" value={data.metrics.topics} icon={metricIcons.topics} />
        <Metric label="Content Items" value={data.metrics.contentItems} icon={metricIcons.contentItems} />
        <Metric label="Publications" value={data.metrics.publications} icon={metricIcons.publications} />
      </section>

      {data.dbError ? (
        <section className="notice">
          <strong>Database unavailable</strong>
          <span>{data.dbError}</span>
        </section>
      ) : null}

      <section className="gridTwo">
        <section className="panel">
          <h2>Recent Runs</h2>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Domain</th>
                  <th>Kind</th>
                  <th>Status</th>
                  <th>Found</th>
                  <th>Fetched</th>
                  <th>Failed</th>
                </tr>
              </thead>
              <tbody>
                {data.runs.map((run) => (
                  <tr key={run.id}>
                    <td>{short(run.domain)}</td>
                    <td>{run.kind}</td>
                    <td><Status value={run.status} /></td>
                    <td>{run.discoveredCount}</td>
                    <td>{run.fetchedCount}</td>
                    <td>{run.failedCount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <h2>Content Pipeline</h2>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Keyword</th>
                  <th>Title</th>
                  <th>Channel</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.content.map((item) => (
                  <tr key={item.id}>
                    <td>{short(item.keyword)}</td>
                    <td>{short(item.seoTitle)}</td>
                    <td>{item.channel}</td>
                    <td><Status value={item.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </>
  );
}

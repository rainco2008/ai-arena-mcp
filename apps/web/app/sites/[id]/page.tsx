import Link from "next/link";
import { runTask, updateSiteStatus } from "@/lib/actions";
import { getSiteDetailData } from "@/lib/data";
import { Metric, Status, metricIcons, short } from "../../_components";

export const dynamic = "force-dynamic";

export default async function SiteDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await getSiteDetailData(id);

  if (!data.site) {
    return (
      <section className="notice">
        <strong>Site unavailable</strong>
        <span>{data.siteError}</span>
      </section>
    );
  }

  const site = data.site;

  return (
    <>
      <section className="panel">
        <div className="panelHead">
          <div>
            <h1>{site.name || site.domain}</h1>
            <p className="panelSub">{site.baseUrl}</p>
          </div>
          <div className="buttonRow">
            <Link className="iconButton" href="/sites">Back</Link>
            <form action={runTask} className="buttonRow">
              <input type="hidden" name="base_url" value={site.baseUrl} />
              <button name="task" value="crawl-discover">Discover</button>
              <button name="task" value="crawl-process">Process</button>
            </form>
          </div>
        </div>

        <div className="metricGrid compactMetrics">
          <Metric label="URLs" value={data.metrics.urls} icon={metricIcons.queuedUrls} />
          <Metric label="Queued" value={data.metrics.queued} icon={metricIcons.queuedUrls} />
          <Metric label="Pages" value={data.metrics.pages} icon={metricIcons.pages} />
          <Metric label="Failed" value={data.metrics.failed} icon={metricIcons.contentItems} />
        </div>

        <dl className="settingsList">
          <dt>Status</dt>
          <dd><Status value={site.status} /></dd>
          <dt>Allowed Domains</dt>
          <dd>{short(site.allowedDomains, 160)}</dd>
          <dt>Crawl Policy</dt>
          <dd>{short(site.crawlPolicy, 220)}</dd>
        </dl>

        <div className="buttonRow siteActions">
          {["active", "paused", "blocked"].map((status) => (
            <form key={status} action={updateSiteStatus}>
              <input type="hidden" name="site_id" value={site.id} />
              <button name="status" value={status} disabled={site.status === status}>
                {status}
              </button>
            </form>
          ))}
        </div>
      </section>

      <section className="gridTwo">
        <section className="panel">
          <h2>Recent Runs</h2>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
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
          <h2>Recent URLs</h2>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>URL</th>
                  <th>Status</th>
                  <th>Attempts</th>
                </tr>
              </thead>
              <tbody>
                {data.urls.map((url) => (
                  <tr key={url.id}>
                    <td>{short(url.url, 120)}</td>
                    <td><Status value={url.status} /></td>
                    <td>{url.attempts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </section>

      <section className="panel">
        <h2>Collected Pages</h2>
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>HTTP</th>
                <th>Quality</th>
                <th>Fetched</th>
              </tr>
            </thead>
            <tbody>
              {data.pages.map((page) => (
                <tr key={page.id}>
                  <td><Link href={`/pages/${page.id}`}>{short(page.title || page.url, 140)}</Link></td>
                  <td>{page.httpStatus ?? "-"}</td>
                  <td>{page.qualityScore}</td>
                  <td>{short(page.fetchedAt, 24)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

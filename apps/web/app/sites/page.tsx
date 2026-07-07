import { runTask } from "@/lib/actions";
import { getDashboardData } from "@/lib/data";
import { Status, short } from "../_components";
import Link from "next/link";
import { Plus } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function SitesPage() {
  const data = await getDashboardData();

  return (
    <section className="panel">
      <div className="panelHead">
        <div>
          <h1>Sites</h1>
          <p className="panelSub">Registered website resources and crawl status.</p>
        </div>
        <div className="buttonRow">
          <Link className="iconButton" href="/sites/new"><Plus size={16} /> New Site</Link>
          <form action={runTask} className="buttonRow">
            <input name="base_url" placeholder="https://example.com" />
            <button name="task" value="crawl-discover">Discover</button>
            <button name="task" value="crawl-process">Process</button>
          </form>
        </div>
      </div>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Domain</th>
              <th>Base URL</th>
              <th>Status</th>
              <th>Discovered</th>
              <th>Crawled</th>
            </tr>
          </thead>
          <tbody>
            {data.sites.map((site) => (
              <tr key={site.id}>
                <td><Link href={`/sites/${site.id}`}>{short(site.domain)}</Link></td>
                <td>{short(site.baseUrl, 100)}</td>
                <td><Status value={site.status} /></td>
                <td>{short(site.lastDiscoveredAt, 24)}</td>
                <td>{short(site.lastCrawledAt, 24)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

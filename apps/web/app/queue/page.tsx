import { getDashboardData } from "@/lib/data";
import { updateUrlStatus } from "@/lib/actions";
import { Status, short } from "../_components";

export const dynamic = "force-dynamic";

export default async function QueuePage() {
  const data = await getDashboardData();

  return (
    <section className="panel">
      <h1>URL Queue</h1>
      <p className="panelSub">Recently discovered URLs awaiting fetch or already processed.</p>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Domain</th>
              <th>URL</th>
              <th>Source</th>
              <th>Priority</th>
              <th>Status</th>
              <th>Attempts</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.urls.map((url) => (
              <tr key={url.id}>
                <td>{short(url.domain)}</td>
                <td>{short(url.url, 120)}</td>
                <td>{short(url.source)}</td>
                <td>{url.priority}</td>
                <td><Status value={url.status} /></td>
                <td>{url.attempts}</td>
                <td>
                  <div className="actionRow">
                    <form action={updateUrlStatus}>
                      <input type="hidden" name="url_id" value={url.id} />
                      <button name="status" value="queued" disabled={url.status === "queued"}>Retry</button>
                    </form>
                    <form action={updateUrlStatus}>
                      <input type="hidden" name="url_id" value={url.id} />
                      <button name="status" value="ignored" disabled={url.status === "ignored"}>Ignore</button>
                    </form>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

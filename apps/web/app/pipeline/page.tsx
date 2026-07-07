import { getDashboardData } from "@/lib/data";
import { Status, short } from "../_components";

export const dynamic = "force-dynamic";

export default async function PipelinePage() {
  const data = await getDashboardData();

  return (
    <section className="panel">
      <h1>Content Pipeline</h1>
      <p className="panelSub">Topics, drafts, review state, and publication progress.</p>
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
                <td>{short(item.seoTitle, 110)}</td>
                <td>{item.channel}</td>
                <td><Status value={item.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

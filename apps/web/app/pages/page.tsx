import { getDashboardData } from "@/lib/data";
import { short } from "../_components";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function PagesPage() {
  const data = await getDashboardData();

  return (
    <section className="panel">
      <h1>Collected Pages</h1>
      <p className="panelSub">Fetched pages, quality score, and summary generation metadata.</p>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Domain</th>
              <th>Title</th>
              <th>HTTP</th>
              <th>Quality</th>
              <th>Summary</th>
              <th>Fetched</th>
            </tr>
          </thead>
          <tbody>
            {data.pages.map((page) => (
              <tr key={page.id}>
                <td>{short(page.domain)}</td>
                <td><Link href={`/pages/${page.id}`}>{short(page.title || page.url, 110)}</Link></td>
                <td>{page.httpStatus ?? "-"}</td>
                <td>{page.qualityScore}</td>
                <td>{short(page.summaryModel)}</td>
                <td>{short(page.fetchedAt, 24)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

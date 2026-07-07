import Link from "next/link";
import { updateUrlStatus } from "@/lib/actions";
import { getPageDetailData } from "@/lib/data";
import { Status, short } from "../../_components";

export const dynamic = "force-dynamic";

function block(value: unknown, fallback = "-") {
  const text = value === null || value === undefined || value === "" ? fallback : String(value);
  return text.length > 6000 ? `${text.slice(0, 6000)}...` : text;
}

export default async function PageDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await getPageDetailData(id);

  if (!data.page) {
    return (
      <section className="notice">
        <strong>Page unavailable</strong>
        <span>{data.pageError}</span>
      </section>
    );
  }

  const page = data.page;

  return (
    <>
      <section className="panel">
        <div className="panelHead">
          <div>
            <h1>{short(page.title || page.url, 120)}</h1>
            <p className="panelSub">{page.url}</p>
          </div>
          <div className="buttonRow">
            <Link className="iconButton" href="/pages">Back</Link>
            {data.site ? <Link className="iconButton" href={`/sites/${data.site.id}`}>Site</Link> : null}
          </div>
        </div>

        <dl className="settingsList">
          <dt>Status</dt>
          <dd><Status value={page.status} /></dd>
          <dt>HTTP</dt>
          <dd>{page.httpStatus ?? "-"}</dd>
          <dt>Quality</dt>
          <dd>{page.qualityScore}</dd>
          <dt>Canonical</dt>
          <dd>{short(page.canonicalUrl, 160)}</dd>
          <dt>Language</dt>
          <dd>{short(page.language)}</dd>
          <dt>Author</dt>
          <dd>{short(page.author)}</dd>
          <dt>Published</dt>
          <dd>{short(page.publishedAt, 32)}</dd>
          <dt>Fetched</dt>
          <dd>{short(page.fetchedAt, 32)}</dd>
          <dt>Summary Model</dt>
          <dd>{short(page.summaryModel)}</dd>
        </dl>

        {data.url ? (
          <div className="buttonRow siteActions">
            <span className="panelSub">URL status: <Status value={data.url.status} /></span>
            <form action={updateUrlStatus}>
              <input type="hidden" name="url_id" value={data.url.id} />
              <button name="status" value="queued" disabled={data.url.status === "queued"}>Retry</button>
            </form>
            <form action={updateUrlStatus}>
              <input type="hidden" name="url_id" value={data.url.id} />
              <button name="status" value="ignored" disabled={data.url.status === "ignored"}>Ignore</button>
            </form>
          </div>
        ) : null}
      </section>

      <section className="gridTwo">
        <section className="panel">
          <h2>Summary</h2>
          <p className="detailText">{block(page.summary)}</p>
        </section>
        <section className="panel">
          <h2>Embeddings</h2>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Provider</th>
                  <th>Model</th>
                  <th>Dim</th>
                </tr>
              </thead>
              <tbody>
                {data.embeddings.map((embedding) => (
                  <tr key={embedding.id}>
                    <td>{embedding.sourceField}</td>
                    <td>{short(embedding.provider)}</td>
                    <td>{short(embedding.model, 44)}</td>
                    <td>{embedding.dimension ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </section>

      <section className="panel">
        <h2>Markdown</h2>
        <pre className="contentPreview">{block(page.markdown)}</pre>
      </section>
    </>
  );
}

import { Download, Search, UploadCloud } from "lucide-react";
import { deployWorkflowTemplate } from "@/lib/actions";
import { getTemplateExplorerData } from "@/lib/data";
import { listValue, short } from "../_components";

export const dynamic = "force-dynamic";

function pageHref(query: string, page: number) {
  const params = new URLSearchParams();
  if (query) params.set("template_query", query);
  params.set("page", String(page));
  return `/templates?${params.toString()}`;
}

export default async function TemplatesPage({
  searchParams,
}: {
  searchParams?: Promise<{ template_query?: string; page?: string }>;
}) {
  const params = await searchParams;
  const query = params?.template_query || "";
  const page = Number(params?.page || "1");
  const templateData = await getTemplateExplorerData(query, page, 25);

  return (
    <section className="panel">
      <div className="panelHead">
        <div>
          <h1>n8n Workflow Templates</h1>
          <p className="panelSub">
            {templateData.total} templates from Zie619/n8n-workflows across {templateData.categories} categories.
          </p>
        </div>
        <form className="templateSearch">
          <Search size={16} />
          <input name="template_query" placeholder="Search: webhook slack approval" defaultValue={templateData.query} />
          <button type="submit">Search</button>
        </form>
      </div>

      {templateData.templateError ? (
        <section className="notice">
          <strong>Template index unavailable</strong>
          <span>{templateData.templateError}</span>
        </section>
      ) : null}

      <div className="categoryStrip">
        {templateData.topCategories.map((category) => (
          <a key={category.category || "uncategorized"} href={pageHref(category.category || "", 1)}>
            {category.category || "Uncategorized"} <span>{category.count}</span>
          </a>
        ))}
      </div>

      <div className="pager">
        <span>
          Page {templateData.page} of {templateData.totalPages} · {templateData.totalMatches} matches
        </span>
        <div>
          <a className={templateData.page <= 1 ? "disabledLink" : "iconButton"} href={pageHref(templateData.query, Math.max(1, templateData.page - 1))}>
            Previous
          </a>
          <a className={templateData.page >= templateData.totalPages ? "disabledLink" : "iconButton"} href={pageHref(templateData.query, Math.min(templateData.totalPages, templateData.page + 1))}>
            Next
          </a>
        </div>
      </div>

      <div className="tableWrap">
        <table className="templateTable">
          <thead>
            <tr>
              <th>Name</th>
              <th>Category</th>
              <th>Nodes</th>
              <th>Triggers</th>
              <th>Node Types</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {templateData.templates.map((template) => (
              <tr key={template.id}>
                <td>
                  <strong>{short(template.name, 72)}</strong>
                  <span className="rowHint">{short(template.sourcePath, 86)}</span>
                </td>
                <td>{short(template.category)}</td>
                <td>{template.nodeCount}</td>
                <td>{listValue(template.triggers)}</td>
                <td>{listValue(template.nodeTypes, 4)}</td>
                <td>
                  <div className="actionRow">
                    <form action={deployWorkflowTemplate}>
                      <input type="hidden" name="template_id" value={template.id} />
                      <button type="submit" title="Deploy to n8n through the n8n API">
                        <UploadCloud size={15} /> Deploy
                      </button>
                    </form>
                    <a className="iconButton" href={`/api/n8n-templates/${template.id}/export`}>
                      <Download size={15} /> JSON
                    </a>
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

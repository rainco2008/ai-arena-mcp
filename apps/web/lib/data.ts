import { count, desc, eq, sql } from "drizzle-orm";
import { db } from "./db/client";
import {
  contentItems,
  crawlPageEmbeddings,
  crawlPages,
  crawlRuns,
  crawlSites,
  crawlUrls,
  n8nWorkflowTemplates,
  publicationRecords,
  resourceTaskLogs,
  resourceTasks,
  researchAssets,
  topicPool,
} from "./db/schema";

export async function getDashboardData() {
  try {
    const [
      siteCount,
      queuedUrlCount,
      pageCount,
      embeddingCount,
      topicCount,
      assetCount,
      contentCount,
      publicationCount,
      sites,
      runs,
      urls,
      pages,
      topics,
      content,
    ] = await Promise.all([
      db.select({ value: count() }).from(crawlSites),
      db.select({ value: count() }).from(crawlUrls).where(eq(crawlUrls.status, "queued")),
      db.select({ value: count() }).from(crawlPages),
      db.select({ value: count() }).from(crawlPageEmbeddings),
      db.select({ value: count() }).from(topicPool),
      db.select({ value: count() }).from(researchAssets),
      db.select({ value: count() }).from(contentItems),
      db.select({ value: count() }).from(publicationRecords),
      db.select().from(crawlSites).orderBy(desc(crawlSites.updatedAt)).limit(20),
      db
        .select({
          id: crawlRuns.id,
          kind: crawlRuns.kind,
          status: crawlRuns.status,
          startedAt: crawlRuns.startedAt,
          finishedAt: crawlRuns.finishedAt,
          discoveredCount: crawlRuns.discoveredCount,
          queuedCount: crawlRuns.queuedCount,
          fetchedCount: crawlRuns.fetchedCount,
          failedCount: crawlRuns.failedCount,
          domain: crawlSites.domain,
          baseUrl: crawlSites.baseUrl,
        })
        .from(crawlRuns)
        .leftJoin(crawlSites, eq(crawlRuns.siteId, crawlSites.id))
        .orderBy(desc(crawlRuns.startedAt))
        .limit(20),
      db
        .select({
          id: crawlUrls.id,
          url: crawlUrls.url,
          source: crawlUrls.source,
          priority: crawlUrls.priority,
          status: crawlUrls.status,
          attempts: crawlUrls.attempts,
          lastError: crawlUrls.lastError,
          discoveredAt: crawlUrls.discoveredAt,
          domain: crawlSites.domain,
        })
        .from(crawlUrls)
        .leftJoin(crawlSites, eq(crawlUrls.siteId, crawlSites.id))
        .orderBy(desc(crawlUrls.discoveredAt))
        .limit(60),
      db
        .select({
          id: crawlPages.id,
          title: crawlPages.title,
          url: crawlPages.url,
          httpStatus: crawlPages.httpStatus,
          qualityScore: crawlPages.qualityScore,
          summaryModel: crawlPages.summaryModel,
          fetchedAt: crawlPages.fetchedAt,
          domain: crawlSites.domain,
        })
        .from(crawlPages)
        .leftJoin(crawlSites, eq(crawlPages.siteId, crawlSites.id))
        .orderBy(desc(crawlPages.fetchedAt))
        .limit(60),
      db.select().from(topicPool).orderBy(desc(topicPool.createdAt)).limit(30),
      db
        .select({
          id: contentItems.id,
          channel: contentItems.channel,
          seoTitle: contentItems.seoTitle,
          status: contentItems.status,
          updatedAt: contentItems.updatedAt,
          keyword: topicPool.keyword,
        })
        .from(contentItems)
        .leftJoin(topicPool, eq(contentItems.topicId, topicPool.id))
        .orderBy(desc(contentItems.updatedAt))
        .limit(30),
    ]);

    const vectorStats = await db.execute(sql`
      select
        count(*)::int as total,
        max(dimension)::int as max_dimension
      from crawl_page_embeddings
      where vector is not null
    `);

    return {
      dbError: null,
      metrics: {
        sites: siteCount[0]?.value ?? 0,
        queuedUrls: queuedUrlCount[0]?.value ?? 0,
        pages: pageCount[0]?.value ?? 0,
        embeddings: embeddingCount[0]?.value ?? 0,
        topics: topicCount[0]?.value ?? 0,
        assets: assetCount[0]?.value ?? 0,
        contentItems: contentCount[0]?.value ?? 0,
        publications: publicationCount[0]?.value ?? 0,
        vectors: Number(vectorStats.rows[0]?.total ?? 0),
        maxVectorDimension: Number(vectorStats.rows[0]?.max_dimension ?? 0),
      },
      sites,
      runs,
      urls,
      pages,
      topics,
      content,
    };
  } catch (error) {
    return {
      dbError: error instanceof Error ? error.message : String(error),
      metrics: {
        sites: 0,
        queuedUrls: 0,
        pages: 0,
        embeddings: 0,
        topics: 0,
        assets: 0,
        contentItems: 0,
        publications: 0,
        vectors: 0,
        maxVectorDimension: 0,
      },
      sites: [],
      runs: [],
      urls: [],
      pages: [],
      topics: [],
      content: [],
    };
  }
}

export type TemplateSearchResult = {
  id: string;
  name: string;
  category: string | null;
  nodeCount: number;
  nodeTypes: unknown;
  triggers: unknown;
  sourcePath: string;
  workflowHash: string;
  score: number;
};

export async function getTaskData(taskId?: string) {
  try {
    const tasks = await db
      .select()
      .from(resourceTasks)
      .orderBy(desc(resourceTasks.createdAt))
      .limit(80);

    const selectedTaskId = taskId || tasks[0]?.id;
    const logs = selectedTaskId
      ? await db
          .select()
          .from(resourceTaskLogs)
          .where(eq(resourceTaskLogs.taskId, selectedTaskId))
          .orderBy(resourceTaskLogs.createdAt)
          .limit(200)
      : [];

    return {
      taskError: null,
      tasks,
      selectedTaskId,
      logs,
    };
  } catch (error) {
    return {
      taskError: error instanceof Error ? error.message : String(error),
      tasks: [],
      selectedTaskId: null,
      logs: [],
    };
  }
}

export async function getSiteDetailData(siteId: string) {
  try {
    const siteRows = await db.select().from(crawlSites).where(eq(crawlSites.id, siteId)).limit(1);
    const site = siteRows[0];
    if (!site) {
      return {
        siteError: "Site not found",
        site: null,
        metrics: { urls: 0, queued: 0, pages: 0, failed: 0 },
        runs: [],
        urls: [],
        pages: [],
      };
    }

    const [urlCount, queuedCount, pageCount, failedCount, runs, urls, pages] = await Promise.all([
      db.select({ value: count() }).from(crawlUrls).where(eq(crawlUrls.siteId, siteId)),
      db
        .select({ value: count() })
        .from(crawlUrls)
        .where(sql`${crawlUrls.siteId} = ${siteId} and ${crawlUrls.status} = 'queued'`),
      db.select({ value: count() }).from(crawlPages).where(eq(crawlPages.siteId, siteId)),
      db
        .select({ value: count() })
        .from(crawlUrls)
        .where(sql`${crawlUrls.siteId} = ${siteId} and ${crawlUrls.status} = 'failed'`),
      db.select().from(crawlRuns).where(eq(crawlRuns.siteId, siteId)).orderBy(desc(crawlRuns.startedAt)).limit(20),
      db.select().from(crawlUrls).where(eq(crawlUrls.siteId, siteId)).orderBy(desc(crawlUrls.discoveredAt)).limit(50),
      db.select().from(crawlPages).where(eq(crawlPages.siteId, siteId)).orderBy(desc(crawlPages.fetchedAt)).limit(50),
    ]);

    return {
      siteError: null,
      site,
      metrics: {
        urls: urlCount[0]?.value ?? 0,
        queued: queuedCount[0]?.value ?? 0,
        pages: pageCount[0]?.value ?? 0,
        failed: failedCount[0]?.value ?? 0,
      },
      runs,
      urls,
      pages,
    };
  } catch (error) {
    return {
      siteError: error instanceof Error ? error.message : String(error),
      site: null,
      metrics: { urls: 0, queued: 0, pages: 0, failed: 0 },
      runs: [],
      urls: [],
      pages: [],
    };
  }
}

export async function getPageDetailData(pageId: string) {
  try {
    const rows = await db
      .select({
        page: crawlPages,
        site: crawlSites,
        url: crawlUrls,
      })
      .from(crawlPages)
      .leftJoin(crawlSites, eq(crawlPages.siteId, crawlSites.id))
      .leftJoin(crawlUrls, eq(crawlPages.urlId, crawlUrls.id))
      .where(eq(crawlPages.id, pageId))
      .limit(1);
    const row = rows[0];
    if (!row) {
      return { pageError: "Page not found", page: null, site: null, url: null, embeddings: [] };
    }
    const embeddings = await db
      .select()
      .from(crawlPageEmbeddings)
      .where(eq(crawlPageEmbeddings.pageId, pageId))
      .orderBy(desc(crawlPageEmbeddings.createdAt));
    return {
      pageError: null,
      page: row.page,
      site: row.site,
      url: row.url,
      embeddings,
    };
  } catch (error) {
    return {
      pageError: error instanceof Error ? error.message : String(error),
      page: null,
      site: null,
      url: null,
      embeddings: [],
    };
  }
}

export async function getTemplateExplorerData(query: string, page = 1, pageSize = 25) {
  const trimmed = query.trim();
  const safePage = Number.isFinite(page) && page > 0 ? Math.floor(page) : 1;
  const safePageSize = Math.min(Math.max(Math.floor(pageSize) || 25, 1), 100);
  const offset = (safePage - 1) * safePageSize;
  try {
    const stats = await db.execute(sql`
      select
        count(*)::int as total,
        count(distinct category)::int as categories
      from n8n_workflow_templates
    `);

    const topCategories = await db.execute(sql`
      select category, count(*)::int as count
      from n8n_workflow_templates
      group by category
      order by count desc, category asc
      limit 8
    `);

    const matchCount = trimmed
      ? await db.execute(sql`
          select count(*)::int as total
          from n8n_workflow_templates
          where to_tsvector('simple', search_text) @@ plainto_tsquery('simple', ${trimmed})
             or search_text ilike ${`%${trimmed.toLowerCase()}%`}
        `)
      : stats;

    const templates = trimmed
      ? await db.execute(sql`
          select
            id,
            name,
            category,
            node_count as "nodeCount",
            node_types as "nodeTypes",
            triggers,
            source_path as "sourcePath",
            workflow_hash as "workflowHash",
            ts_rank(to_tsvector('simple', search_text), plainto_tsquery('simple', ${trimmed}))::float as score
          from n8n_workflow_templates
          where to_tsvector('simple', search_text) @@ plainto_tsquery('simple', ${trimmed})
             or search_text ilike ${`%${trimmed.toLowerCase()}%`}
          order by score desc, node_count asc, name asc
          limit ${safePageSize}
          offset ${offset}
        `)
      : await db
          .select({
            id: n8nWorkflowTemplates.id,
            name: n8nWorkflowTemplates.name,
            category: n8nWorkflowTemplates.category,
            nodeCount: n8nWorkflowTemplates.nodeCount,
            nodeTypes: n8nWorkflowTemplates.nodeTypes,
            triggers: n8nWorkflowTemplates.triggers,
            sourcePath: n8nWorkflowTemplates.sourcePath,
            workflowHash: n8nWorkflowTemplates.workflowHash,
          })
          .from(n8nWorkflowTemplates)
          .orderBy(desc(n8nWorkflowTemplates.nodeCount))
          .limit(safePageSize)
          .offset(offset);

    const totalMatches = Number(matchCount.rows[0]?.total ?? 0);

    return {
      templateError: null,
      query: trimmed,
      page: safePage,
      pageSize: safePageSize,
      total: Number(stats.rows[0]?.total ?? 0),
      totalMatches,
      totalPages: Math.max(1, Math.ceil(totalMatches / safePageSize)),
      categories: Number(stats.rows[0]?.categories ?? 0),
      topCategories: topCategories.rows as Array<{ category: string | null; count: number }>,
      templates: (Array.isArray(templates) ? templates : templates.rows).map((template) => ({
        ...template,
        score: Number((template as Partial<TemplateSearchResult>).score ?? 0),
      })) as TemplateSearchResult[],
    };
  } catch (error) {
    return {
      templateError: error instanceof Error ? error.message : String(error),
      query: trimmed,
      page: safePage,
      pageSize: safePageSize,
      total: 0,
      totalMatches: 0,
      totalPages: 1,
      categories: 0,
      topCategories: [],
      templates: [],
    };
  }
}

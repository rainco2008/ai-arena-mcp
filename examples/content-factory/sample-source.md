# Content Factory Source Brief

This sample document verifies Microsoft MarkItDown ingestion for the local content factory.

## Key Points

- MarkItDown converts files into Markdown for LLM research workflows.
- The content factory stores converted Markdown in `research_assets`.
- n8n can trigger ingestion through the Execute Command node.

## Recommended Workflow

1. Place source documents under `data/inbox`.
2. Create or select a topic in `topic_pool`.
3. Run `ingest-document` with the topic id and file path.
4. Continue with draft generation and quality review.

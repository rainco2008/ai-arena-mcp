CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'crawl_page_embeddings'
      AND column_name = 'vector'
      AND udt_name <> 'vector'
  ) THEN
    ALTER TABLE crawl_page_embeddings
      ALTER COLUMN vector TYPE vector
      USING CASE
        WHEN vector IS NULL OR vector = '' THEN NULL
        ELSE vector::vector
      END;
  END IF;
END $$;

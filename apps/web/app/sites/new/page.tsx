import Link from "next/link";
import { createSite } from "@/lib/actions";

export const dynamic = "force-dynamic";

export default function NewSitePage() {
  return (
    <section className="panel settingsPanel">
      <div className="panelHead">
        <div>
          <h1>New Site</h1>
          <p className="panelSub">Create a website resource and configure its crawl boundaries.</p>
        </div>
        <Link className="iconButton" href="/sites">Back</Link>
      </div>

      <form action={createSite} className="settingsForm siteForm">
        <div className="settingsField">
          <label htmlFor="site-base-url">Base URL</label>
          <input id="site-base-url" name="base_url" placeholder="https://example.com" required />
        </div>
        <div className="settingsField">
          <label htmlFor="site-name">Name</label>
          <input id="site-name" name="name" placeholder="Example" />
        </div>
        <div className="settingsField">
          <label htmlFor="site-allowed-domains">Allowed Domains</label>
          <textarea id="site-allowed-domains" name="allowed_domains" placeholder="example.com" />
        </div>
        <div className="formGrid">
          <div className="settingsField">
            <label htmlFor="site-max-depth">Max Depth</label>
            <input id="site-max-depth" name="max_depth" type="number" min="0" defaultValue="2" />
          </div>
          <div className="settingsField">
            <label htmlFor="site-rate-limit">Rate Limit ms</label>
            <input id="site-rate-limit" name="rate_limit_ms" type="number" min="0" defaultValue="1000" />
          </div>
        </div>
        <label className="checkRow">
          <input name="same_domain_only" type="checkbox" defaultChecked />
          <span>Same domain only</span>
        </label>
        <label className="checkRow">
          <input name="respect_robots_sitemaps" type="checkbox" defaultChecked />
          <span>Respect robots sitemap hints</span>
        </label>
        <button type="submit">Save Site</button>
      </form>
    </section>
  );
}

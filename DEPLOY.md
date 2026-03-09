# Deploying Plat to platmap.org

## Architecture

| Layer | Service | What goes there |
|-------|---------|-----------------|
| Domain | Cloudflare Registrar | platmap.org |
| Static site | Cloudflare Pages | HTML, CSS, JS, data JSON files |
| Large tile files | Cloudflare R2 | tiles/*.pmtiles (5 files, ~856 MB) |
| Tile subdomain | Cloudflare DNS | tiles.platmap.org → R2 bucket |

---

## Step 1 — Create a Cloudflare account

Go to https://dash.cloudflare.com/sign-up and create a free account if you don't have one.

---

## Step 2 — Register platmap.org

1. In the Cloudflare dashboard, go to **Domain Registration → Register Domains**
2. Search for `platmap.org`
3. Purchase it (~$7.48/yr)
4. Cloudflare will automatically add it to your account with DNS managed there

---

## Step 3 — Create the R2 bucket for PMTiles

1. In the Cloudflare dashboard, go to **R2 Object Storage → Create bucket**
2. Name it: `plat-tiles`
3. Location: Automatic (or choose a region close to your users)
4. Once created, click **Settings → Public access → Allow Access** to make it publicly readable

### Upload the 5 PMTiles files

In the `tiles/` folder of this project, upload all 5 files to the bucket:
- `states.pmtiles`
- `counties.pmtiles`
- `tracts_2000.pmtiles`
- `tracts_2010.pmtiles`
- `tracts_2020.pmtiles`

You can upload via the Cloudflare dashboard UI (drag and drop), or install the Wrangler CLI:
```
npm install -g wrangler
wrangler login
wrangler r2 object put plat-tiles/states.pmtiles --file tiles/states.pmtiles
wrangler r2 object put plat-tiles/counties.pmtiles --file tiles/counties.pmtiles
wrangler r2 object put plat-tiles/tracts_2000.pmtiles --file tiles/tracts_2000.pmtiles
wrangler r2 object put plat-tiles/tracts_2010.pmtiles --file tiles/tracts_2010.pmtiles
wrangler r2 object put plat-tiles/tracts_2020.pmtiles --file tiles/tracts_2020.pmtiles
```

### Configure CORS on the R2 bucket

In the bucket **Settings → CORS policy**, add:
```json
[
  {
    "AllowedOrigins": ["https://platmap.org", "https://www.platmap.org"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["Range"],
    "ExposeHeaders": ["Content-Range", "Accept-Ranges", "Content-Length"],
    "MaxAgeSeconds": 86400
  }
]
```

### Connect tiles.platmap.org to the bucket

1. In the bucket **Settings → Custom Domains**, click **Connect Domain**
2. Enter: `tiles.platmap.org`
3. Cloudflare will automatically add the DNS record

---

## Step 4 — Push the code to GitHub

Create a GitHub repository (private or public) and push the project:

```bash
cd "National Dashboard"
git init
git add .
git commit -m "Initial deploy"
git remote add origin https://github.com/YOUR_USERNAME/platmap.git
git push -u origin main
```

The `.gitignore` in this project already excludes:
- `raw_data/` (huge CSVs, not needed for the site)
- `shapefiles/` (GIS source files)
- `downloads/` (raw shapefiles)
- `processed/` (intermediate pipeline outputs)
- `tiles/` (PMTiles go to R2, not GitHub)
- `serve.py` (local dev server only)

---

## Step 5 — Deploy to Cloudflare Pages

1. In the Cloudflare dashboard, go to **Workers & Pages → Create → Pages**
2. Click **Connect to Git** and authorize your GitHub account
3. Select the `platmap` repository
4. Build settings:
   - **Framework preset**: None
   - **Build command**: *(leave blank)*
   - **Build output directory**: `/` (root)
5. Click **Save and Deploy**

Cloudflare Pages will deploy the site and give you a preview URL like `platmap-xyz.pages.dev`.

---

## Step 6 — Add the custom domain

1. In your Pages project, go to **Custom Domains → Set up a custom domain**
2. Enter `platmap.org`
3. Cloudflare will automatically configure the DNS (since the domain is registered with Cloudflare)
4. Also add `www.platmap.org` and set it to redirect to `platmap.org`

---

## Step 7 — Verify

Open https://platmap.org and check:
- [ ] Homepage loads correctly
- [ ] Navigate to Explore → Homebuyers by Race
- [ ] Map loads and census tract data appears when zooming in
- [ ] Year slider works
- [ ] Navigate to Homebuyers by Income and back — state is preserved
- [ ] About, Data, and Methodology pages load with full content

---

## Ongoing updates

When you update the site (new data year, design changes):

```bash
git add .
git commit -m "Update: description of changes"
git push
```

Cloudflare Pages automatically redeploys on every push to `main`. Typically live within 60 seconds.

To update PMTiles (e.g., adding a new year's tract data), re-upload the relevant file to R2:
```bash
wrangler r2 object put plat-tiles/tracts_2020.pmtiles --file tiles/tracts_2020.pmtiles
```

---

## Cost estimate

| Service | Cost |
|---------|------|
| platmap.org domain | ~$7.48/yr |
| Cloudflare Pages | Free |
| Cloudflare R2 (856 MB storage) | Free (10 GB included) |
| R2 bandwidth | Free up to 1M requests/month |
| **Total** | **~$7.48/yr** |

# DNS Sync

GitOps-style DNS management system that syncs DNS records from YAML files to Cloudflare. Changes to YAML files in the `records/` directory automatically trigger updates to your Cloudflare DNS via GitHub Actions.

## Features

- ✅ **GitOps workflow**: DNS records as code in YAML files
- 🔄 **Automatic sync**: GitHub Actions detect and apply changes on push to main
- 🎯 **Selective management**: Only manages records defined in YAML (won't touch other records)
- 🔍 **Smart detection**: Uses git diff to detect creates, updates, and deletes
- 🛡️ **Safe**: Non-destructive to unmanaged records in Cloudflare

## Setup

### 1. Get Cloudflare Credentials

#### Create an API Token
1. Log into your Cloudflare account
2. Go to **My Profile** → **API Tokens**
3. Click **Create Token** → **Create Custom Token**
4. Set permissions:
   - **Zone: Read**
   - **DNS: Edit**
5. Select the zone (domain) this token can access
6. Create and save the token securely

#### Get Your Zone ID
1. Go to your Cloudflare dashboard
2. Select your domain
3. Navigate to **DNS** section
4. Find your **Zone ID** at the bottom right

### 2. Configure GitHub Secrets

Add these secrets to your GitHub repository:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Add the following secrets:
   - `CLOUDFLARE_API_TOKEN`: Your Cloudflare API token
   - `CLOUDFLARE_ZONE_ID`: Your Cloudflare Zone ID

### 3. Define DNS Records

Create YAML files in the `records/` directory. Each file represents one DNS record.

**Example: `records/www.yaml`**
```yaml
name: www.example.com
type: A
content: 192.168.1.1
ttl: 3600
proxied: false
description: Web server A record
```

**Example: `records/mail.yaml`**
```yaml
name: example.com
type: MX
content: mail.example.com
ttl: 3600
priority: 10
description: Primary mail server
```

### 4. Push to Main

Commit and push your changes to the `main` branch. The GitHub Action will automatically:
1. Detect which files were added/modified/deleted
2. Sync those changes to Cloudflare
3. Leave other DNS records untouched

## YAML Schema

### Required Fields
- `name`: Full domain name (e.g., `subdomain.example.com` or `example.com`)
- `type`: DNS record type (`A`, `AAAA`, `CNAME`, `MX`, `TXT`, etc.)
- `content`: Record value (IP address, hostname, text, etc.)

### Optional Fields
- `ttl`: Time to live in seconds (default: `3600`)
- `proxied`: Whether to proxy through Cloudflare (default: `false`)
- `priority`: Priority for MX/SRV records
- `description`: Human-readable description (not synced to Cloudflare)

## How It Works

1. **Git diff detection**: The sync script compares `HEAD~1` and `HEAD` to find changes in `records/`
2. **File-based operations**:
   - **Added file** → Create DNS record in Cloudflare
   - **Modified file** → Update existing DNS record
   - **Deleted file** → Delete DNS record from Cloudflare
3. **Record matching**: Records are matched by `name` + `type` combination
4. **Selective sync**: Only records defined in YAML are managed; others remain untouched

## Local Testing

You can test the sync script locally:

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Add your credentials to `.env`:
   ```
   CLOUDFLARE_API_TOKEN=your_token
   CLOUDFLARE_ZONE_ID=your_zone_id
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the sync script:
   ```bash
   python sync.py
   ```

**Note**: Local testing requires at least 2 commits in git history to compare changes.

## Workflow Trigger

The GitHub Action triggers on:
- Push to `main` branch
- Changes to files in `records/` directory

This means commits that don't touch `records/` won't trigger unnecessary syncs.

## Important Notes

- **Record constraints**:
  - A/AAAA records cannot coexist with CNAME on the same name
  - NS records cannot coexist with any other record type on the same name
- **First commit**: If this is your first commit, the script compares against an empty tree
- **Unmanaged records**: DNS records not defined in YAML files are never modified or deleted

## Example Workflow

```bash
# Add a new subdomain
echo 'name: api.example.com
type: A
content: 10.0.0.5
ttl: 3600
proxied: true
description: API server' > records/api.yaml

git add records/api.yaml
git commit -m "Add API subdomain"
git push origin main
# GitHub Action runs and creates the record in Cloudflare

# Update the record
# Edit records/api.yaml, change content to 10.0.0.6
git add records/api.yaml
git commit -m "Update API server IP"
git push origin main
# GitHub Action runs and updates the record in Cloudflare

# Remove the record
git rm records/api.yaml
git commit -m "Remove API subdomain"
git push origin main
# GitHub Action runs and deletes the record from Cloudflare
```

## License

MIT

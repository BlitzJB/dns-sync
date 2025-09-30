#!/usr/bin/env python3
"""
DNS Sync Script
Syncs DNS records from YAML files to Cloudflare based on git changes
"""

import os
import sys
import json
import yaml
import requests
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set


class CloudflareAPI:
    """Cloudflare API client for DNS operations"""

    def __init__(self, api_token: str, zone_id: str):
        self.api_token = api_token
        self.zone_id = zone_id
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }

    def list_records(self) -> List[Dict]:
        """List all DNS records in the zone"""
        url = f"{self.base_url}/zones/{self.zone_id}/dns_records"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()["result"]

    def create_record(self, record: Dict) -> Dict:
        """Create a new DNS record"""
        url = f"{self.base_url}/zones/{self.zone_id}/dns_records"
        data = {
            "type": record["type"],
            "name": record["name"],
            "content": record["content"],
            "ttl": record.get("ttl", 3600),
            "proxied": record.get("proxied", False)
        }
        if "priority" in record:
            data["priority"] = record["priority"]

        response = requests.post(url, headers=self.headers, json=data)
        response.raise_for_status()
        return response.json()["result"]

    def update_record(self, record_id: str, record: Dict) -> Dict:
        """Update an existing DNS record"""
        url = f"{self.base_url}/zones/{self.zone_id}/dns_records/{record_id}"
        data = {
            "type": record["type"],
            "name": record["name"],
            "content": record["content"],
            "ttl": record.get("ttl", 3600),
            "proxied": record.get("proxied", False)
        }
        if "priority" in record:
            data["priority"] = record["priority"]

        response = requests.patch(url, headers=self.headers, json=data)
        response.raise_for_status()
        return response.json()["result"]

    def delete_record(self, record_id: str) -> None:
        """Delete a DNS record"""
        url = f"{self.base_url}/zones/{self.zone_id}/dns_records/{record_id}"
        response = requests.delete(url, headers=self.headers)
        response.raise_for_status()


class DNSSync:
    """Main DNS sync orchestrator"""

    def __init__(self, api: CloudflareAPI, records_dir: str = "records"):
        self.api = api
        self.records_dir = Path(records_dir)

    def get_changed_files(self) -> Dict[str, Set[str]]:
        """
        Get changed files from git diff
        Returns dict with keys: added, modified, deleted
        """
        # Get the diff between HEAD and HEAD~1 (previous commit)
        # In GitHub Actions, this will compare the pushed commit with its parent
        try:
            result = subprocess.run(
                ["git", "diff", "--name-status", "HEAD~1", "HEAD"],
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError:
            # If HEAD~1 doesn't exist (first commit), compare with empty tree
            result = subprocess.run(
                ["git", "diff", "--name-status", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "HEAD"],
                capture_output=True,
                text=True,
                check=True
            )

        changes = {"added": set(), "modified": set(), "deleted": set()}

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("\t")
            status = parts[0]
            filepath = parts[1]

            # Only process files in records/ directory with .yaml or .yml extension
            if not filepath.startswith(f"{self.records_dir}/"):
                continue
            if not (filepath.endswith(".yaml") or filepath.endswith(".yml")):
                continue

            if status == "A":
                changes["added"].add(filepath)
            elif status == "M":
                changes["modified"].add(filepath)
            elif status == "D":
                changes["deleted"].add(filepath)

        return changes

    def load_yaml_record(self, filepath: str) -> Dict:
        """Load a DNS record from a YAML file"""
        with open(filepath, 'r') as f:
            record = yaml.safe_load(f)

        # Validate required fields
        required = ["name", "type", "content"]
        for field in required:
            if field not in record:
                raise ValueError(f"Missing required field '{field}' in {filepath}")

        return record

    def find_matching_record(self, yaml_record: Dict, cf_records: List[Dict]) -> Optional[Dict]:
        """
        Find a Cloudflare record matching the YAML record
        Match based on name and type
        """
        for cf_record in cf_records:
            if (cf_record["name"] == yaml_record["name"] and
                cf_record["type"] == yaml_record["type"]):
                return cf_record
        return None

    def records_differ(self, yaml_record: Dict, cf_record: Dict) -> bool:
        """Check if YAML record differs from Cloudflare record"""
        fields = ["content", "ttl", "proxied"]
        for field in fields:
            yaml_value = yaml_record.get(field)
            cf_value = cf_record.get(field)

            # Handle ttl default
            if field == "ttl":
                yaml_value = yaml_value or 3600
                cf_value = cf_value or 3600

            # Handle proxied default
            if field == "proxied":
                yaml_value = yaml_value if yaml_value is not None else False
                cf_value = cf_value if cf_value is not None else False

            if yaml_value != cf_value:
                return True

        # Check priority for MX, SRV records
        if yaml_record["type"] in ["MX", "SRV"]:
            if yaml_record.get("priority") != cf_record.get("priority"):
                return True

        return False

    def sync(self):
        """Main sync operation"""
        print("🔍 Detecting changes...")
        changes = self.get_changed_files()

        if not any(changes.values()):
            print("✅ No DNS record changes detected")
            return

        print(f"📝 Changes detected:")
        print(f"  Added: {len(changes['added'])}")
        print(f"  Modified: {len(changes['modified'])}")
        print(f"  Deleted: {len(changes['deleted'])}")
        print()

        # Fetch current Cloudflare records
        print("☁️  Fetching current Cloudflare DNS records...")
        cf_records = self.api.list_records()
        print(f"   Found {len(cf_records)} existing records in Cloudflare")
        print()

        # Process deletions
        for filepath in changes["deleted"]:
            print(f"🗑️  Processing deletion: {filepath}")
            try:
                # For deleted files, we need to get the record info from git history
                result = subprocess.run(
                    ["git", "show", f"HEAD~1:{filepath}"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                yaml_record = yaml.safe_load(result.stdout)

                cf_record = self.find_matching_record(yaml_record, cf_records)
                if cf_record:
                    self.api.delete_record(cf_record["id"])
                    print(f"   ✅ Deleted: {yaml_record['name']} ({yaml_record['type']})")
                else:
                    print(f"   ⚠️  Record not found in Cloudflare: {yaml_record['name']} ({yaml_record['type']})")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            print()

        # Process additions
        for filepath in changes["added"]:
            print(f"➕ Processing addition: {filepath}")
            try:
                yaml_record = self.load_yaml_record(filepath)

                # Check if record already exists (shouldn't, but let's be safe)
                cf_record = self.find_matching_record(yaml_record, cf_records)
                if cf_record:
                    print(f"   ⚠️  Record already exists, will update instead")
                    if self.records_differ(yaml_record, cf_record):
                        self.api.update_record(cf_record["id"], yaml_record)
                        print(f"   ✅ Updated: {yaml_record['name']} ({yaml_record['type']})")
                    else:
                        print(f"   ℹ️  No changes needed")
                else:
                    self.api.create_record(yaml_record)
                    print(f"   ✅ Created: {yaml_record['name']} ({yaml_record['type']})")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            print()

        # Process modifications
        for filepath in changes["modified"]:
            print(f"📝 Processing modification: {filepath}")
            try:
                yaml_record = self.load_yaml_record(filepath)

                cf_record = self.find_matching_record(yaml_record, cf_records)
                if cf_record:
                    if self.records_differ(yaml_record, cf_record):
                        self.api.update_record(cf_record["id"], yaml_record)
                        print(f"   ✅ Updated: {yaml_record['name']} ({yaml_record['type']})")
                    else:
                        print(f"   ℹ️  No changes needed")
                else:
                    # Record doesn't exist, create it
                    print(f"   ⚠️  Record not found, will create")
                    self.api.create_record(yaml_record)
                    print(f"   ✅ Created: {yaml_record['name']} ({yaml_record['type']})")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            print()

        print("🎉 Sync complete!")


def main():
    # Load environment variables
    api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    zone_id = os.getenv("CLOUDFLARE_ZONE_ID")

    if not api_token or not zone_id:
        print("❌ Error: CLOUDFLARE_API_TOKEN and CLOUDFLARE_ZONE_ID must be set")
        sys.exit(1)

    # Initialize API and sync
    api = CloudflareAPI(api_token, zone_id)
    sync = DNSSync(api)

    try:
        sync.sync()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

import os
import json
import re
import time
import requests


FIGMA_API = "https://api.figma.com/v1"
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "figma", "cache")
CACHE_TTL = 300  # 5 minutes — avoids rate limits


def parse_figma_url(url: str) -> dict:
    """
    Parse a Figma URL and extract file key and optional node ID.

    Supports these URL formats:
      https://www.figma.com/file/FILEKEY/Title
      https://www.figma.com/design/FILEKEY/Title
      https://www.figma.com/design/FILEKEY/Title?node-id=123-456
      https://www.figma.com/proto/FILEKEY/Title
      Just a bare file key (backwards compat)
    """
    url = url.strip()

    # If it's already a bare file key (no slashes, no dots), return as-is
    if re.match(r'^[A-Za-z0-9]+$', url):
        return {"file_key": url, "node_id": None}

    # Match Figma URL patterns: /file/, /design/, /proto/
    match = re.search(r'figma\.com/(?:file|design|proto)/([A-Za-z0-9]+)', url)
    if not match:
        raise ValueError(
            f"Invalid Figma URL: {url}\n"
            "Expected format: https://www.figma.com/design/FILEKEY/Title"
        )

    file_key = match.group(1)

    # Extract node-id from query params if present
    node_id = None
    node_match = re.search(r'node-id=([^&]+)', url)
    if node_match:
        # Figma uses "123-456" in URLs but "123:456" in API
        node_id = node_match.group(1).replace('-', ':')

    return {"file_key": file_key, "node_id": node_id}


class FigmaClient:
    def __init__(self):
        self.token = os.environ.get("FIGMA_ACCESS_TOKEN")

        # Support both FIGMA_URL (full link) and legacy FIGMA_FILE_KEY
        figma_url = os.environ.get("FIGMA_URL", "")
        if figma_url:
            parsed = parse_figma_url(figma_url)
            self.file_key = parsed["file_key"]
            self.node_id = parsed["node_id"]
        else:
            # Backwards compatibility
            self.file_key = os.environ.get("FIGMA_FILE_KEY", "")
            self.node_id = None

        self.headers = {"X-Figma-Token": self.token}
        os.makedirs(CACHE_DIR, exist_ok=True)

    def _request_with_retry(self, url, params=None, max_retries=3):
        """Make a GET request with retry on rate limit (429)."""
        for attempt in range(max_retries):
            resp = requests.get(url, headers=self.headers, params=params)
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"  Figma rate limited. Waiting {wait}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        raise Exception("Figma API rate limit exceeded after retries. Try again in a few minutes.")

    def get_file(self) -> dict:
        """Fetch the Figma file data (cached to avoid rate limits).
        If a node_id was parsed from the URL, fetches only that subtree.
        """
        cache_suffix = f"_{self.node_id.replace(':', '-')}" if self.node_id else ""
        cache_path = os.path.join(CACHE_DIR, f"{self.file_key}{cache_suffix}_file.json")

        # Return cached if fresh
        if os.path.exists(cache_path):
            age = time.time() - os.path.getmtime(cache_path)
            if age < CACHE_TTL:
                with open(cache_path, "r") as f:
                    return json.load(f)

        url = f"{FIGMA_API}/files/{self.file_key}"
        params = {}
        if self.node_id:
            params["ids"] = self.node_id

        resp = self._request_with_retry(url, params=params)
        data = resp.json()

        # Cache it
        with open(cache_path, "w") as f:
            json.dump(data, f)

        return data

    def get_frame_ids(self) -> list:
        """Get all top-level frame IDs from the file.
        If a node_id was specified in the URL, only returns frames under that node.
        """
        data = self.get_file()
        doc = data.get("document", {})
        frame_ids = []

        def _collect_frames(node, page_name=""):
            """Recursively collect FRAME nodes."""
            if node.get("type") == "FRAME":
                frame_ids.append({
                    "id": node["id"],
                    "name": node.get("name", ""),
                    "page": page_name,
                })
            for child in node.get("children", []):
                child_page = page_name if page_name else node.get("name", "")
                _collect_frames(child, child_page)

        for page in doc.get("children", []):
            _collect_frames(page, page.get("name", ""))

        return frame_ids

    def export_images(self, node_ids: list, scale: int = 2) -> dict:
        """
        Export frames as PNG images. Returns dict of {node_id: local_file_path}.
        Downloads and caches images locally.
        """
        # Check which images we already have cached
        to_export = []
        cached = {}
        for nid in node_ids:
            safe_id = nid.replace(":", "-")
            local_path = os.path.join(CACHE_DIR, f"{safe_id}.png")
            if os.path.exists(local_path):
                age = time.time() - os.path.getmtime(local_path)
                if age < CACHE_TTL:
                    cached[nid] = local_path
                    continue
            to_export.append(nid)

        # Export missing ones from Figma API
        if to_export:
            ids_str = ",".join(to_export)
            resp = self._request_with_retry(
                f"{FIGMA_API}/images/{self.file_key}",
                params={"ids": ids_str, "scale": scale, "format": "png"},
            )
            images = resp.json().get("images", {})

            # Download each image
            for nid, url in images.items():
                if url:
                    safe_id = nid.replace(":", "-")
                    local_path = os.path.join(CACHE_DIR, f"{safe_id}.png")
                    img_resp = requests.get(url)
                    if img_resp.status_code == 200:
                        with open(local_path, "wb") as f:
                            f.write(img_resp.content)
                        cached[nid] = local_path

        return cached

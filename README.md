# filesir-async-client

[فارسی 🇮🇷](README.fa.md) · English

Asynchronous Python 3.10+ client for the [Files.ir](https://files.ir) REST API.

Built on `httpx.AsyncClient` and `pydantic` v2. Provides typed coroutines for every endpoint
in the OpenAPI spec, automatic Bearer-token injection, configurable retry + exponential
backoff, and a high-level `upload_file` helper that auto-selects the right session-based
upload strategy (`single`, `s3-single`, `s3-multipart`, `tus`).

## Install

From PyPI (when published):

```bash
pip install filesir-async-client
```

Directly from this Git repository (recommended for now):

```bash
pip install "git+https://github.com/loopy-iri/aiofilesir.git"
```

Pin to a tag or branch:

```bash
pip install "git+https://github.com/loopy-iri/aiofilesir.git@v0.1.0"
pip install "git+https://github.com/loopy-iri/aiofilesir.git@main"
```

Add to `requirements.txt`:

```
filesir-async-client @ git+https://github.com/loopy-iri/aiofilesir.git@main
```

## Quick start

```python
import asyncio
from filesir import FilesIrClient


async def main() -> None:
    async with FilesIrClient(access_token="pat_...") as client:
        usage = await client.storage.space_usage()
        print(usage.used, usage.available, usage.remaining)

        folder = await client.folders.create(name="reports")

        entry = await client.uploads.upload_file(
            "/tmp/big-video.mp4",
            parent_id=folder.id,
            progress=lambda done, total: print(f"{done}/{total}"),
        )

        # Build a direct GET URL with the access token in the query string.
        url = client.files.direct_download_url(entry.id)
        print("Direct URL:", url)

        await client.files.download_to_file(entry.id, "/tmp/copy.mp4")


asyncio.run(main())
```

## Authentication

```python
# From an existing personal access token (account settings > developers).
client = FilesIrClient(access_token="pat_...")

# Or login by email/password and receive a token automatically.
client = await FilesIrClient.from_credentials(
    email="me@example.com",
    password="secret",
    token_name="my-script",
)
```

## Resources

- `client.auth` — register / login
- `client.storage` — space usage
- `client.files` — list / update / delete / move / duplicate / restore / download / `direct_download_url`
- `client.folders` — create folder
- `client.uploads` — `upload_file()` (auto-strategy) / `upload_legacy()` / low-level sessions
- `client.sharing` — share / change-permissions / unshare
- `client.starring` — star / unstar
- `client.links` — shareable links
- `client.workspaces` — CRUD + members + invites + activity logs
- `client.tags` — list / attach / detach / sync

## Live test script

`examples/live_upload_and_link.py` uploads a real file, prints the direct
download URL and creates a public shareable link. Pass your token via the
`FILESIR_TOKEN` environment variable (or edit `FALLBACK_TOKEN` inside the
script):

```bash
export FILESIR_TOKEN=pat_xxxxxxxxxxxx
python examples/live_upload_and_link.py /path/to/local-file.png
```

## License

MIT.

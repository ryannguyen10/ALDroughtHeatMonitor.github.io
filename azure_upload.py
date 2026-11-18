"""
Upload the Alabama S2S pipeline outputs to Azure Blob Storage.

Authentication (picked automatically, first match wins):
  1. AZURE_STORAGE_CONNECTION_STRING env var   -> quick testing with an account key
  2. AZURE_STORAGE_ACCOUNT_URL env var          -> DefaultAzureCredential
     (Managed Identity on the Azure VM, or `az login` on a laptop)

Required for option 2: the compute node's identity needs the
"Storage Blob Data Contributor" role on the storage account (or container).

pip install azure-storage-blob azure-identity
"""

import os
import mimetypes
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from azure.storage.blob import BlobServiceClient, ContentSettings


def get_container_client(container_name):
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")  # https://<account>.blob.core.windows.net

    if conn_str:
        service = BlobServiceClient.from_connection_string(conn_str)
    elif account_url:
        from azure.identity import DefaultAzureCredential
        service = BlobServiceClient(account_url, credential=DefaultAzureCredential())
    else:
        raise RuntimeError(
            "Set AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_URL."
        )

    container = service.get_container_client(container_name)
    if not container.exists():
        container.create_container()
    return container


def upload_file(local_path, container_name, blob_name, overwrite=True):
    """Upload one file to an exact blob name (e.g. a stable 'latest' URL)."""
    local_path = Path(local_path)
    container = get_container_client(container_name)
    ctype = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
    with open(local_path, "rb") as fh:
        container.upload_blob(
            name=blob_name,
            data=fh,
            overwrite=overwrite,
            content_settings=ContentSettings(content_type=ctype),
        )
    print(f"Uploaded {local_path.name} -> {container_name}/{blob_name}")
    return blob_name


def upload_directory(
    local_dir,
    container_name,
    blob_prefix="",
    exclude_dirs=("raw",),
    overwrite=True,
    max_workers=8,
):
    """
    Upload every file under local_dir, keeping the folder structure.

    local_dir/report/figures/fig1.png -> <blob_prefix>/report/figures/fig1.png

    Returns a list of uploaded blob names. Raises if any file fails, so a
    scheduled run shows as failed instead of silently losing outputs.
    """
    local_dir = Path(local_dir)
    container = get_container_client(container_name)

    files = [
        p for p in local_dir.rglob("*")
        if p.is_file()
        and not any(part in exclude_dirs for part in p.relative_to(local_dir).parts)
    ]

    def _upload(path):
        rel = path.relative_to(local_dir).as_posix()
        blob_name = f"{blob_prefix.strip('/')}/{rel}" if blob_prefix else rel
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            container.upload_blob(
                name=blob_name,
                data=fh,
                overwrite=overwrite,
                content_settings=ContentSettings(content_type=ctype),
            )
        return blob_name

    uploaded, failed = [], []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_upload, p): p for p in files}
        for fut in as_completed(futures):
            try:
                uploaded.append(fut.result())
            except Exception as exc:
                failed.append((futures[fut], exc))

    print(f"Uploaded {len(uploaded)} files to '{container_name}/{blob_prefix}'")
    if failed:
        for p, exc in failed:
            print(f"  FAILED {p}: {exc}")
        raise RuntimeError(f"{len(failed)} file(s) failed to upload")
    return uploaded

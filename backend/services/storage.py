"""Private Supabase Storage via the existing HTTP client; stream uploads/downloads."""
import asyncio
import os
from urllib.parse import quote

import httpx

BUCKET = "saylo-audio"


class StorageError(RuntimeError):
    pass


class AudioStorage:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/") + "/storage/v1"
        self.key = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.key:
            raise StorageError("audio_storage_not_configured")
        self.headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}

    def object_url(self, key):
        return f"{self.url}/object/{BUCKET}/{quote(key, safe='/')}"

    async def check_private(self):
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{self.url}/bucket/{BUCKET}", headers=self.headers)
        if response.status_code != 200 or response.json().get("public") is not False:
            raise StorageError("private_audio_bucket_unavailable")

    async def upload(self, key, path, size):
        await self.check_private()
        if path.stat().st_size != size:
            raise StorageError("audio_size_mismatch")

        async def chunks():
            with path.open("rb") as stream:
                while chunk := await asyncio.to_thread(stream.read, 65536):
                    yield chunk

        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(self.object_url(key), content=chunks(), headers={
                **self.headers, "Content-Type": "application/octet-stream", "Content-Length": str(size), "x-upsert": "false"})
        if response.status_code not in (200, 201) and not await self.exists(key, size):
            raise StorageError("audio_upload_failed")

    async def exists(self, key, size):
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.head(self.object_url(key), headers=self.headers)
        # Supabase's HEAD exists API uses both 400 and 404 for absent objects
        # (the official storage-js client handles both).
        if response.status_code in (400, 404): return False
        if response.status_code != 200: raise StorageError("audio_storage_unavailable")
        return response.headers.get("content-length") == str(size)

    async def download(self, key, path, expected_size):
        from services.limits import MAX_AUDIO_BYTES
        if expected_size <= 0 or expected_size > MAX_AUDIO_BYTES:
            raise StorageError("audio_size_mismatch")
        size = 0
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream("GET", self.object_url(key), headers=self.headers) as response:
                if response.status_code != 200: raise StorageError("audio_download_failed")
                with path.open("wb") as stream:
                    async for chunk in response.aiter_bytes(65536):
                        size += len(chunk)
                        if size > expected_size: raise StorageError("audio_size_mismatch")
                        await asyncio.to_thread(stream.write, chunk)
        if size != expected_size: raise StorageError("audio_size_mismatch")

    async def delete(self, key):
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.request("DELETE", f"{self.url}/object/{BUCKET}", headers=self.headers,
                                            json={"prefixes": [key]})
        if response.status_code not in (200, 204, 404):
            raise StorageError("audio_delete_failed")

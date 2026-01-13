# Building Custom Backends

> Implementing custom storage solutions for specialized needs

## Overview

Backends handle the virtual filesystem operations. While built-in backends (State, Store, Filesystem) cover most cases, you may need custom backends for specialized storage requirements.

## Backend Protocol

Every backend must implement this protocol:

```python
from typing import Protocol, Optional

class BackendProtocol(Protocol):
    """Protocol that all backends must implement."""

    def read(self, path: str) -> Optional[str]:
        """
        Read file contents.

        Args:
            path: Absolute path starting with /

        Returns:
            File contents as string, or None if not found
        """
        ...

    def write(self, path: str, contents: str) -> None:
        """
        Write contents to file.

        Args:
            path: Absolute path starting with /
            contents: String content to write
        """
        ...

    def delete(self, path: str) -> bool:
        """
        Delete a file.

        Args:
            path: Absolute path starting with /

        Returns:
            True if deleted, False if not found
        """
        ...

    def list(self, path: str) -> list[str]:
        """
        List directory contents.

        Args:
            path: Absolute directory path

        Returns:
            List of file/directory names (not full paths)
        """
        ...

    def exists(self, path: str) -> bool:
        """
        Check if path exists.

        Args:
            path: Absolute path starting with /

        Returns:
            True if exists, False otherwise
        """
        ...

    def is_directory(self, path: str) -> bool:
        """
        Check if path is a directory.

        Args:
            path: Absolute path starting with /

        Returns:
            True if directory, False if file or not exists
        """
        ...
```

## Creating a Custom Backend

### Example: Redis Backend

```python
import redis
from typing import Optional
import json

class RedisBackend:
    """Backend storing files in Redis for distributed access."""

    def __init__(self, redis_url: str, prefix: str = "deepagent"):
        self.client = redis.from_url(redis_url)
        self.prefix = prefix

    def _key(self, path: str) -> str:
        """Convert path to Redis key."""
        return f"{self.prefix}:{path}"

    def _dir_key(self, path: str) -> str:
        """Key for directory listings."""
        return f"{self.prefix}:dir:{path}"

    def read(self, path: str) -> Optional[str]:
        result = self.client.get(self._key(path))
        return result.decode() if result else None

    def write(self, path: str, contents: str) -> None:
        # Store file content
        self.client.set(self._key(path), contents)

        # Update parent directory listing
        parent = "/".join(path.split("/")[:-1]) or "/"
        filename = path.split("/")[-1]
        self.client.sadd(self._dir_key(parent), filename)

    def delete(self, path: str) -> bool:
        existed = self.client.delete(self._key(path)) > 0

        # Update parent directory listing
        if existed:
            parent = "/".join(path.split("/")[:-1]) or "/"
            filename = path.split("/")[-1]
            self.client.srem(self._dir_key(parent), filename)

        return existed

    def list(self, path: str) -> list[str]:
        members = self.client.smembers(self._dir_key(path))
        return [m.decode() for m in members]

    def exists(self, path: str) -> bool:
        return self.client.exists(self._key(path)) > 0

    def is_directory(self, path: str) -> bool:
        # Check if any files exist under this path
        return self.client.exists(self._dir_key(path)) > 0


# Usage
from deepagents import create_deep_agent

agent = create_deep_agent(
    backend=RedisBackend("redis://localhost:6379"),
    system_prompt="Agent with Redis-backed storage..."
)
```

### Example: S3 Backend

```python
import boto3
from typing import Optional

class S3Backend:
    """Backend storing files in Amazon S3."""

    def __init__(self, bucket: str, prefix: str = ""):
        self.s3 = boto3.client('s3')
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    def _s3_key(self, path: str) -> str:
        """Convert virtual path to S3 key."""
        clean_path = path.lstrip("/")
        if self.prefix:
            return f"{self.prefix}/{clean_path}"
        return clean_path

    def read(self, path: str) -> Optional[str]:
        try:
            response = self.s3.get_object(
                Bucket=self.bucket,
                Key=self._s3_key(path)
            )
            return response['Body'].read().decode('utf-8')
        except self.s3.exceptions.NoSuchKey:
            return None

    def write(self, path: str, contents: str) -> None:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=self._s3_key(path),
            Body=contents.encode('utf-8')
        )

    def delete(self, path: str) -> bool:
        try:
            self.s3.delete_object(
                Bucket=self.bucket,
                Key=self._s3_key(path)
            )
            return True
        except:
            return False

    def list(self, path: str) -> list[str]:
        prefix = self._s3_key(path)
        if not prefix.endswith("/"):
            prefix += "/"

        response = self.s3.list_objects_v2(
            Bucket=self.bucket,
            Prefix=prefix,
            Delimiter="/"
        )

        items = []
        # Files
        for obj in response.get('Contents', []):
            name = obj['Key'].replace(prefix, "").split("/")[0]
            if name:
                items.append(name)
        # Directories
        for prefix_obj in response.get('CommonPrefixes', []):
            name = prefix_obj['Prefix'].replace(prefix, "").rstrip("/")
            if name:
                items.append(name + "/")

        return list(set(items))

    def exists(self, path: str) -> bool:
        try:
            self.s3.head_object(
                Bucket=self.bucket,
                Key=self._s3_key(path)
            )
            return True
        except:
            return False

    def is_directory(self, path: str) -> bool:
        prefix = self._s3_key(path)
        if not prefix.endswith("/"):
            prefix += "/"

        response = self.s3.list_objects_v2(
            Bucket=self.bucket,
            Prefix=prefix,
            MaxKeys=1
        )
        return response.get('KeyCount', 0) > 0
```

### Example: Encrypted Backend

```python
from cryptography.fernet import Fernet
from typing import Optional

class EncryptedBackend:
    """Wrapper that encrypts all file contents."""

    def __init__(self, inner_backend, encryption_key: bytes):
        self.inner = inner_backend
        self.fernet = Fernet(encryption_key)

    def read(self, path: str) -> Optional[str]:
        encrypted = self.inner.read(path)
        if encrypted is None:
            return None
        return self.fernet.decrypt(encrypted.encode()).decode()

    def write(self, path: str, contents: str) -> None:
        encrypted = self.fernet.encrypt(contents.encode()).decode()
        self.inner.write(path, encrypted)

    def delete(self, path: str) -> bool:
        return self.inner.delete(path)

    def list(self, path: str) -> list[str]:
        return self.inner.list(path)

    def exists(self, path: str) -> bool:
        return self.inner.exists(path)

    def is_directory(self, path: str) -> bool:
        return self.inner.is_directory(path)


# Usage: Wrap any backend with encryption
from deepagents.backends.state import StateBackend

key = Fernet.generate_key()
encrypted_backend = EncryptedBackend(
    StateBackend(runtime),
    key
)
```

## Backend Design Patterns

### Pattern 1: Caching Layer

```python
class CachingBackend:
    """Adds caching to any backend."""

    def __init__(self, inner_backend, cache_size: int = 100):
        self.inner = inner_backend
        self.cache = {}  # Simple LRU could be added
        self.cache_size = cache_size

    def read(self, path: str) -> Optional[str]:
        if path in self.cache:
            return self.cache[path]

        result = self.inner.read(path)
        if result is not None:
            self._cache_put(path, result)
        return result

    def write(self, path: str, contents: str) -> None:
        self.inner.write(path, contents)
        self._cache_put(path, contents)

    def delete(self, path: str) -> bool:
        self.cache.pop(path, None)
        return self.inner.delete(path)

    def _cache_put(self, path: str, contents: str):
        if len(self.cache) >= self.cache_size:
            # Simple eviction: remove first item
            self.cache.pop(next(iter(self.cache)))
        self.cache[path] = contents
```

### Pattern 2: Audit Logging

```python
class AuditBackend:
    """Logs all file operations for compliance."""

    def __init__(self, inner_backend, audit_log_path: str):
        self.inner = inner_backend
        self.audit_log = audit_log_path

    def _log(self, operation: str, path: str, **kwargs):
        import datetime
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "operation": operation,
            "path": path,
            **kwargs
        }
        with open(self.audit_log, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def read(self, path: str) -> Optional[str]:
        result = self.inner.read(path)
        self._log("read", path, found=result is not None)
        return result

    def write(self, path: str, contents: str) -> None:
        self._log("write", path, size=len(contents))
        self.inner.write(path, contents)

    def delete(self, path: str) -> bool:
        result = self.inner.delete(path)
        self._log("delete", path, success=result)
        return result
```

### Pattern 3: Versioned Backend

```python
class VersionedBackend:
    """Keeps version history of all files."""

    def __init__(self, inner_backend, max_versions: int = 10):
        self.inner = inner_backend
        self.max_versions = max_versions

    def write(self, path: str, contents: str) -> None:
        # Save current version before overwriting
        current = self.inner.read(path)
        if current is not None:
            version = self._next_version(path)
            self.inner.write(f"{path}.v{version}", current)
            self._cleanup_old_versions(path)

        self.inner.write(path, contents)

    def get_version(self, path: str, version: int) -> Optional[str]:
        return self.inner.read(f"{path}.v{version}")

    def list_versions(self, path: str) -> list[int]:
        parent = "/".join(path.split("/")[:-1]) or "/"
        filename = path.split("/")[-1]
        files = self.inner.list(parent)
        versions = []
        for f in files:
            if f.startswith(f"{filename}.v"):
                try:
                    v = int(f.split(".v")[-1])
                    versions.append(v)
                except:
                    pass
        return sorted(versions)
```

## Testing Custom Backends

```python
def test_backend_protocol(backend):
    """Test that a backend implements the protocol correctly."""

    # Test write and read
    backend.write("/test.txt", "hello")
    assert backend.read("/test.txt") == "hello"

    # Test exists
    assert backend.exists("/test.txt")
    assert not backend.exists("/nonexistent.txt")

    # Test list
    backend.write("/dir/file1.txt", "a")
    backend.write("/dir/file2.txt", "b")
    files = backend.list("/dir")
    assert "file1.txt" in files
    assert "file2.txt" in files

    # Test is_directory
    assert backend.is_directory("/dir")
    assert not backend.is_directory("/test.txt")

    # Test delete
    assert backend.delete("/test.txt")
    assert not backend.exists("/test.txt")
    assert not backend.delete("/nonexistent.txt")

    print("All backend tests passed!")
```

## Related Tutorials

- [Backend Selection Guide](08_backend_selection.md)
- [Composite Backend Routing](20_composite_routing.md)
- [Long-Term Memory](05_long_term_memory.md)

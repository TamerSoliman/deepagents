# Composite Backend Routing

> Directing file operations to different backends based on path

## Overview

CompositeBackend routes file operations to different backends based on path prefixes. This enables mixed storage strategies within a single agent.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COMPOSITE BACKEND                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  File Operation: read_file("/memories/preferences.md")                       │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                         PATH ROUTER                                      │ │
│  │                                                                          │ │
│  │  Routes:                                                                 │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐│ │
│  │  │ "/memories/"  ──────────────────────► StoreBackend (persistent)     ││ │
│  │  │ "/templates/" ──────────────────────► FilesystemBackend (disk)      ││ │
│  │  │ "/cache/"     ──────────────────────► StateBackend (ephemeral)      ││ │
│  │  │ "/*" (default) ─────────────────────► StateBackend (ephemeral)      ││ │
│  │  └─────────────────────────────────────────────────────────────────────┘│ │
│  │                                                                          │ │
│  │  Match: "/memories/" prefix                                              │ │
│  │       │                                                                  │ │
│  │       ▼                                                                  │ │
│  │  Forward to StoreBackend                                                 │ │
│  │  with path: "/memories/preferences.md"                                   │ │
│  │                                                                          │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Basic Configuration

```python
from deepagents import create_deep_agent
from deepagents.backends.composite import CompositeBackend
from deepagents.backends.state import StateBackend
from deepagents.backends.store import StoreBackend
from deepagents.backends.filesystem import FilesystemBackend

agent = create_deep_agent(
    backend=lambda runtime: CompositeBackend(
        default=StateBackend(runtime),
        routes={
            "/memories/": StoreBackend(runtime),
            "/templates/": FilesystemBackend(root_dir="/app/templates"),
        }
    ),
    store=persistent_store,  # Required for StoreBackend
    system_prompt="Agent with composite storage..."
)
```

## Route Matching

### Prefix Matching

Routes match by longest prefix:

```python
routes = {
    "/data/": BackendA,
    "/data/cache/": BackendB,
    "/data/cache/temp/": BackendC,
}

# Path matching:
"/data/file.txt"           → BackendA (matches /data/)
"/data/cache/item.txt"     → BackendB (matches /data/cache/)
"/data/cache/temp/x.txt"   → BackendC (matches /data/cache/temp/)
"/other/file.txt"          → default backend (no match)
```

### Trailing Slash Convention

```python
# With trailing slash: matches directory and contents
"/memories/": StoreBackend
# Matches: /memories/file.txt, /memories/sub/file.txt

# Without trailing slash: matches exact path
"/config": ConfigBackend
# Matches: /config only (not /config/file.txt)
```

## Common Routing Patterns

### Pattern 1: Persistence Hybrid

```python
# Ephemeral scratch, persistent memories
routes = {
    "/memories/": StoreBackend(runtime),   # Persists across sessions
    "/scratch/": StateBackend(runtime),    # Cleared each session
}
default = StateBackend(runtime)            # Default ephemeral

# Usage in system prompt:
system_prompt = """
- Write temporary work to /scratch/
- Save lasting information to /memories/
- Memories persist, scratch is cleared
"""
```

### Pattern 2: Read-Only Templates

```python
# Templates on disk (read-only), work in state
routes = {
    "/templates/": FilesystemBackend(
        root_dir="/app/templates",
        read_only=True  # Prevent modifications
    ),
}
default = StateBackend(runtime)

# Agent can read templates but not modify them
```

### Pattern 3: Multi-Tenant Isolation

```python
def create_tenant_backend(tenant_id: str):
    return CompositeBackend(
        default=StateBackend(runtime),
        routes={
            "/shared/": StoreBackend(runtime, namespace="shared"),
            "/private/": StoreBackend(runtime, namespace=f"tenant_{tenant_id}"),
        }
    )

# Each tenant has isolated private storage
# but shared access to common resources
```

### Pattern 4: Tiered Storage

```python
routes = {
    # Hot tier: Fast, ephemeral
    "/cache/": StateBackend(runtime),

    # Warm tier: Persistent, in-memory database
    "/data/": StoreBackend(runtime),

    # Cold tier: Disk storage, slow but unlimited
    "/archive/": FilesystemBackend(root_dir="/mnt/archive"),
}

# System prompt guides usage:
system_prompt = """
Storage tiers:
- /cache/: Fast access, cleared each session
- /data/: Persistent, limited size
- /archive/: Long-term storage, slower access
"""
```

### Pattern 5: External Integration

```python
from my_backends import S3Backend, RedisBackend

routes = {
    "/cloud/": S3Backend(bucket="my-bucket"),
    "/cache/": RedisBackend(url="redis://localhost"),
    "/memories/": StoreBackend(runtime),
}
default = StateBackend(runtime)

# Mix internal and external storage seamlessly
```

## Routing Visualization

```
                                    COMPOSITE BACKEND
                                          │
              ┌───────────────────────────┼───────────────────────────┐
              │                           │                           │
              ▼                           ▼                           ▼
        ┌──────────┐               ┌──────────┐               ┌──────────┐
        │/memories/│               │/templates│               │ default  │
        └────┬─────┘               └────┬─────┘               └────┬─────┘
             │                          │                          │
             ▼                          ▼                          ▼
      ┌────────────┐            ┌────────────┐            ┌────────────┐
      │StoreBackend│            │Filesystem  │            │StateBackend│
      │            │            │Backend     │            │            │
      │ Persistent │            │ Read-only  │            │ Ephemeral  │
      │ Cross-sess │            │ Disk-based │            │ In-memory  │
      └────────────┘            └────────────┘            └────────────┘
```

## Path Transformation

By default, paths are passed through unchanged. You can transform them:

```python
class PrefixStrippingBackend:
    """Strips route prefix before forwarding."""

    def __init__(self, inner_backend, prefix: str):
        self.inner = inner_backend
        self.prefix = prefix

    def read(self, path: str) -> Optional[str]:
        # Strip prefix: /memories/file.txt → /file.txt
        inner_path = path[len(self.prefix)-1:]
        return self.inner.read(inner_path)

    # ... other methods similarly transform path

# Usage
routes = {
    "/memories/": PrefixStrippingBackend(
        StoreBackend(runtime),
        prefix="/memories/"
    )
}
# /memories/preferences.md becomes /preferences.md in StoreBackend
```

## Cross-Backend Operations

### Listing Across Backends

```python
# ls("/") shows files from ALL backends
# Composite merges results

ls("/")
# Returns combined listing:
#   memories/   (from StoreBackend)
#   templates/  (from FilesystemBackend)
#   scratch/    (from StateBackend)
#   file.txt    (from default StateBackend)
```

### Moving Between Backends

```python
# Moving from ephemeral to persistent
system_prompt = """
To persist temporary work:
1. read_file("/scratch/work.md")
2. write_file("/memories/work.md", content)
3. delete("/scratch/work.md")

This moves data from StateBackend to StoreBackend.
"""
```

## Configuration Best Practices

### 1. Clear Path Conventions

```python
system_prompt = """
## Storage Locations

/memories/  - Persistent user preferences and history
/templates/ - Read-only document templates
/research/  - Current research findings (session-only)
/output/    - Final outputs (session-only)

Always use the appropriate location for data type.
"""
```

### 2. Document Backend Characteristics

```python
system_prompt = """
## Storage Characteristics

| Path        | Persists | Writable | Speed  |
|-------------|----------|----------|--------|
| /memories/  | Yes      | Yes      | Medium |
| /templates/ | Yes      | No       | Fast   |
| /research/  | No       | Yes      | Fast   |
"""
```

### 3. Handle Backend Failures

```python
class ResilientCompositeBackend:
    """Falls back to default on route backend failure."""

    def read(self, path: str) -> Optional[str]:
        backend = self._get_backend(path)
        try:
            return backend.read(path)
        except Exception:
            # Fall back to default
            return self.default.read(path)
```

## Related Tutorials

- [Backend Selection Guide](08_backend_selection.md)
- [Building Custom Backends](19_custom_backends.md)
- [Long-Term Memory](05_long_term_memory.md)

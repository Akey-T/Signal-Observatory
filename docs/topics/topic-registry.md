# Topic Registry operations

## Purpose and ownership

The Topic Registry defines the stable subjects that Signal Observatory may monitor. Human-reviewed YAML under `config/topics/` is authoritative. Keywords discovered in observations may become review candidates, but never become canonical topics automatically.

The initial registry contains 100 topics in five domains, 15 hierarchical categories, curated aliases, and explicit mappings for arXiv, GitHub, Hacker News, and Wikipedia. A mapping is configuration only; E02 performs no external request.

## File schema

Every `.yaml` or `.yml` file contains:

```yaml
schema_version: 1
categories:
  - name: AI Systems
    slug: ai-systems
    description: Applied AI systems and operational practices.
topics:
  - canonical_name: Model Context Protocol
    slug: model-context-protocol
    description: An open protocol connecting AI applications to tools and contextual data.
    category: ai-systems
    status: active
    monitoring_priority: 95
    aliases:
      - value: MCP
        type: abbreviation
        match_mode: exact
        case_sensitive: true
        status: active
        confidence: 1.0
    sources:
      github:
        enabled: true
        search_queries: [modelcontextprotocol]
allowed_alias_collisions: []
```

Unknown fields and sources fail validation. Slugs use lowercase kebab-case. Priority and confidence are bounded. Enabled source mappings require values. Category references and parent graphs must be valid.

Normalization applies Unicode NFKC, trims and collapses whitespace, and case-folds insensitive aliases. It deliberately preserves punctuation, so `C`, `C++`, `C#`, `.NET`, and `Node.js` remain distinct. A case-sensitive alias preserves case after whitespace and Unicode normalization.

## Add or change a topic

1. Choose one existing category or add a reviewed category.
2. Add a stable canonical name, unique slug, useful description, explicit status and priority.
3. Add only aliases that genuinely identify the same subject. Choose type, match mode, case sensitivity, and confidence deliberately.
4. Add explicit source mappings. Do not copy a generic keyword list into every source.
5. Run `topics validate`, then `topics diff`, then `topics sync --dry-run`.
6. Review changes and warnings before applying `topics sync --applied-by <identity>`.

Changing file order does not change the checksum. A semantic change does. Successful changed syncs increment the registry version and write per-entity before/after audit rows.

## Collision and lifecycle policy

Alias ambiguity is an error by default. A real shared alias can be accepted only with an explicit entry listing the exact topic slugs and a review reason:

```yaml
allowed_alias_collisions:
  - alias: MCP
    topics: [model-context-protocol, microsoft-certified-professional]
    reason: Reviewed acronym shared by two established concepts.
```

An accepted collision remains visible as a validation warning, registry-version metadata, an audit review entry, and a warning data-quality check.

Never delete a Topic to retire it. Set `status: deprecated`; sync records `deprecated_at`. Removing a topic, alias, mapping, or category from YAML does not delete its database row. Diff reports it as orphaned so an operator can resolve the mismatch without destroying historical relationships.

## Sync and failure behavior

- `validate` reads files only.
- `diff` reads validated YAML and database state only.
- `sync --dry-run` always rolls back.
- `sync` applies categories, topics, aliases, mappings, version, audit, and data-quality rows in one transaction.
- Any exception rolls back the whole transaction.
- A second sync of unchanged content creates no version and no audit rows.

Quality records include topic count, active topic count, alias count, unmapped topics, accepted duplicate aliases, orphaned database topics, topics without aliases, and topics without any source mapping. These counts describe registry integrity; they are not Trend Score inputs.

Status semantics are deliberately conservative: `active` is eligible for normal collection,
`paused` temporarily stops new collection while retaining history, and `deprecated` retires the
concept as an independent monitoring subject without deleting it. Monitoring priority is an
operator scheduling hint: 90–100 critical, 70–89 high, 40–69 normal, 1–39 low, and 0 disabled for
discovery priority. It is not a popularity measurement.

## Metric semantics

- Topic is not a keyword.
- Alias is not an independent Topic.
- Source Mapping is configuration and not an observation.
- Monitoring Priority is not Trend Score.
- Deprecated does not mean deleted.

## API and observability

The Topic API is read-only and shares the CLI query service. Registry status exposes latest version, checksum, sync time, row counts, and warning count. Operator identity is stored in `topic_registry_versions.applied_by`; audit rows capture entity type, stable key, action, and before/after JSON.

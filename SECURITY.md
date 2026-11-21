# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| `0.1.x` | :white_check_mark: |
| `main`  | :white_check_mark: |

---

## Security Architecture & Defense in Depth

This server is designed to allow LLM agents to inspect SQLite databases safely. Because autonomous models can generate arbitrary SQL queries, the system employs a strict 4-layer defense model where no single layer is relied upon as a single point of failure:

1. **Layer 1: Driver / OS Filesystem (VFS `mode=ro`)**
   Connections are opened strictly using SQLite URI filenames percent-encoded via `Path.resolve().as_uri() + "?mode=ro"`. This prevents writes at the operating system file descriptor and virtual file system (VFS) layer. Even if internal SQL checks were bypassed, the filesystem driver rejects any write attempt with `sqlite3.OperationalError: attempt to write a readonly database`.

2. **Layer 2: Native Engine Authorizer (`conn.set_authorizer`)**
   A native SQLite C authorizer callback hook inspects every action before the database engine compiles or plans the query. Any action attempting to insert, update, delete, drop, alter, attach, detach, or modify database pragma state is intercepted and returned `SQLITE_DENY`.

3. **Layer 3: Pragma Enforcement (`PRAGMA query_only = ON`)**
   Activated immediately upon database connection creation, locking the SQLite engine state to query-only mode.

4. **Layer 4: Query Statement Validation**
   Queries are inspected to ensure they start strictly with allowed read keywords (`SELECT`, `EXPLAIN`, `WITH`). Stacked statements (multiple SQL statements separated by semicolons) are blocked across all SQLite quotation formats (single quotes, double quotes, bracketed identifiers `[...]`, and backticks `` `...` ``).

### Additional Operational Safeguards
* **Virtual Machine Instruction Limiting:** Runaway queries (e.g., circular recursive CTEs or unindexed Cartesian joins) are bounded by SQLite's virtual machine progress handler (`SQLITE_MAX_INSTRUCTIONS`, default 10,000,000 instructions) to prevent resource exhaustion.
* **Safe Serialization:** Binary `BLOB` fields are formatted as `<BLOB N bytes>`, and oversized text cells are truncated at 500 characters to bound response size and prevent JSON serialization errors (`TypeError`).
* **Stdio Hygiene:** All application diagnostics and error logging are routed strictly to `sys.stderr`, guaranteeing that `sys.stdout` remains uncorrupted JSON-RPC 2.0 frames.

---

## Scope & Access Boundaries

* **Database-Wide Read Access:** The server provides read-only access to all user tables and views in the opened database. There is currently no table-level allowlist or row-level redaction mechanism.
* **Untrusted Database Content in Prompts:** Schema names, column names, and raw DDL injected into the `analyze_schema` prompt template originate from the database file and are treated as untrusted text. Schema content is dynamically enclosed in an outer markdown code fence longer than any backtick sequence in the schema (at least 4 backticks). This prevents inner code blocks (such as ```` ```sql ```` DDL) or identifier backticks from closing the block early, mitigating structural formatting breakouts. Note that enclosing untrusted content in fences reduces formatting-based injection but does not neutralize semantic prompt injection (instruction text embedded in schema names or focus arguments); LLM clients must treat prompt inputs from untrusted databases accordingly.

---

## Threat Model

| Threat | Mitigating Layer |
| --- | --- |
| Mutation queries (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`) | Layers 1, 2, 3, 4 |
| Multi-statement injection (`SELECT 1; DROP TABLE users;`) | Layer 4 (Scanner) & Layer 2 (Authorizer) |
| Special characters in database paths (`#`, `?`, `%`) attempting URI injection | Layer 1 (RFC 3986 Percent-Encoding) |
| SQL injection via identifiers with apostrophes (`it's_table`) | Parameterized table-valued PRAGMA functions (`pragma_table_info(?)`) |
| Denial of Service via unindexed joins or runaway CTEs | Step progress handler instruction limits |
| Data corruption or JSON-RPC protocol hijacking via stdout prints | Protocol isolation (`sys.stderr` exclusive logging) |
| Formatting breakouts via database identifiers in DBA prompt | Dynamic multi-backtick fencing and whitespace flattening; reduces formatting breakouts but does not neutralize semantic instruction text |

---

## Reporting a Vulnerability

If you discover a security vulnerability or bypass in any defense layer, please do **not** open a public issue.

Instead, please report it privately:
* **GitHub:** Through the [GitHub Security Advisory private reporting form](https://github.com/ccarrott/Read-Only-SQLite-MCP-Server/security/advisories/new) on the repository.
* **Email:** [sethwhitfield113@gmail.com](mailto:sethwhitfield113@gmail.com)

Please include:
1. Description of the vulnerability and attack vector.
2. Minimal SQL query or reproduction script demonstrating the bypass.
3. Impact assessment on the affected defense layers.

Reports will be acknowledged promptly, and a fix will be published in a patch release before public disclosure.

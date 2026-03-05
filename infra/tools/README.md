## Tooling Layout

- `joern-cli/`: Joern runtime trimmed for Java scanning in CodeScope.
- Source baseline: `E:\CodeScope_test\joern-cli`.
- Kept directories: `bin/`, `conf/`, `lib/`, `scripts/`, `schema-extender/`, `frontends/javasrc2cpg/`, `frontends/jimple2cpg/`.
- Excluded runtime/cache content: `workspace/`, `__pycache__/`, and non-Java frontend payloads.

This layout keeps external scan dependencies self-contained while avoiding unnecessary binary footprint.

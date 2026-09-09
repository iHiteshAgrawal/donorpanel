# DonorPanel

Multi-agent donor coordination for patients who need matched blood repeatedly, for life.

Patients with thalassemia, sickle cell disease and rare phenotypes need matched blood on a recurring basis. The pool of donors who can match them is systematically smaller than the population that needs them, because matching follows ancestry and donor registries do not mirror their patients. Registries are large but mostly unreachable, so the recruiting burden falls on families, permanently.

DonorPanel holds the donor network so no family has to browse it, and does the asking so no family has to.

## Status

Early scaffolding. Channels, configuration and the matching policy layer are in place. The agent architecture is not yet decided.

## Quick start

```
uv venv && uv pip install -e ".[dev]"
cp .env.example .env
.venv/bin/donorpanel status
.venv/bin/python -m pytest tests -q
```

Without credentials only the console channel is active, which is enough to run the tests.

## Layout

| Path | Purpose |
| --- | --- |
| `src/donorpanel/channels` | Outreach transports behind one interface |
| `src/donorpanel/policies` | Condition rules as YAML, not code |
| `src/donorpanel/agents` | Pending architecture decision |
| `src/donorpanel/nodes` | Deterministic graph nodes |
| `src/donorpanel/tools` | Tool functions |

See [AGENT.md](AGENT.md) for full context, scope and conventions.

## License

MIT

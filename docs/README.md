# Travel Assistant: documentation

A personal AI assistant for Indian domestic flights. It searches live fares, checks fare rules and
passenger rights with citations, remembers your preferences, and is measured by an eval suite. It
was built to demonstrate **MCP server design, RAG, agent construction, and evals** end to end.

| Doc | What's in it |
|---|---|
| [architecture.md](architecture.md) | The big picture: components, data flow, boundaries |
| [mcp-server.md](mcp-server.md) | The `travel-mcp` server: tools, providers, caching, quotas, validation, preferences |
| [rag.md](rag.md) | Policy knowledge base: sources, ingestion, extraction, chunking, hybrid retrieval, freshness |
| [agent.md](agent.md) | The Claude Agent SDK planner: workflow prompt, guardrails, traces, auth |
| [evals.md](evals.md) | How the agent is measured: cases, checks, grounding, running and reading results |
| [decisions.md](decisions.md) | Why things are the way they are (API choices, trade-offs), in order |
| [setup.md](setup.md) | Windows setup from scratch, Claude Desktop connection |
| [operations.md](operations.md) | Quotas, costs, refreshing sources, troubleshooting |
| [roadmap.md](roadmap.md) | Known gaps and what's next |

If you're new, read them in this order: architecture → decisions → whichever component you're touching.

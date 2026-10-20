# Related products

Research date: 20 October 2026. This is a focused review of official product documentation, not a complete market survey or a pricing/licensing evaluation.

| Product | Verified overlap | Implication for FlowReuse |
| --- | --- | --- |
| Windmill | AI Flow Chat can build/modify connected flows using scripts from the workspace or hub; AI Fix assists with execution errors. | Closest documented match to code-centered reuse plus AI construction and repair. |
| n8n | AI Workflow Builder creates, refines and debugs workflows from natural-language requirements, including node selection, placement and configuration. | A chat-to-canvas experience alone is not a distinguishing feature. |
| Sim | In-workflow conversations are scoped to the workflow; chat supports building, editing, testing and debugging workflows. | A compact context-aware copilot is already an established interaction pattern. |
| Dify | DSL import/export captures application configuration, workflow orchestration and model settings; applications can be duplicated independently. | A versioned portable definition is also an established pattern. |

## Sources

- [Windmill AI](https://www.windmill.dev/windmill_ai): code assistance, AI Fix, script reuse, flow construction and automatic connections.
- [Windmill flow architecture](https://www.windmill.dev/docs/flows/architecture): JSON-serializable OpenFlow definitions and script references.
- [n8n AI Workflow Builder](https://docs.n8n.io/build/ways-of-building-workflows/ai-workflow-builder): conversational workflow creation, refinement and debugging.
- [Sim Chat](https://docs.sim.ai/chat): workflow-scoped conversation and supported workflow operations.
- [Dify application management](https://docs.dify.ai/en/cloud/use-dify/workspace/app-management): independent variations and DSL import/export.

## Product judgment

The user's idea has substantial existing overlap. Windmill deserves an especially close hands-on comparison before investing in broad script/runtime capabilities. The product hypothesis for FlowReuse is the combination of deterministic repeat execution, project-local model selection, compact external-agent invocation, and a freshly generated project skill contract after each invocation.

That hypothesis is an inference, not a verified uniqueness claim. The cited pages do not establish that competitors lack per-invocation skill generation. A deeper evaluation should test actual agent integrations, recovery semantics, extension cost and measured token/context savings with the same real task.

## Format decision

FlowReuse uses versioned JSON, JSON Schema and conventional English SKILL.md instructions rather than introducing a new parser or executable language. The `.frskill.json` name identifies the contract. Refreshing the package snapshots current capabilities and revision references; it does not invoke AI or regenerate working code. Existing vendor formats are useful references, not claimed interchange formats.

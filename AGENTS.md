
# Vietherb GraphRAG — Agent Instructions

## Project
Develop an evidence-grounded GraphRAG system for Vietnamese medicinal plants using Vietherb OWL/RDF and Neo4j.

## Environment
- Windows 11
- Root: D:\vietherb_rag
- Python: 3.15
- RDFLib: 7.6.0
- Neo4j driver: 6.4.1
- Neo4j Desktop data: D:\Neo4jData
- Git default branch: main

## Mandatory workflow
1. Read docs/PROJECT_CONTEXT.md and docs/HANDOFF.md before starting.
2. Inspect git status before changing files.
3. Explain the intended modifications before implementation.
4. Preserve RDF/OWL semantics and original IRIs.
5. Preserve provenance and enable reproducible experiments.
6. Never invent ontology entities, relations, or medical evidence.
7. Write tests for new parsing and mapping logic.
8. Run relevant tests and report exact results.
9. Update docs/HANDOFF.md after each completed task.

## Safety
- Keep all project files on drive D.
- Never delete or reset Neo4j databases without approval.
- Never commit credentials, .env files, or private research datasets.
- Do not overwrite existing files without inspection.
- Do not push code to remote repositories without approval.

## Research standards
- Separate ontology assertions from inferred knowledge.
- Distinguish source-grounded claims from clinical evidence.
- Record source hashes, software versions, and experiment settings.
- Support controlled comparisons and ablation studies.
- Never fabricate evaluation metrics or experimental results.

## Language
Communicate in Vietnamese.
Use English for code identifiers and technical conventions.

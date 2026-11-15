
# Vietherb GraphRAG — Project Context

## Research objective
Develop an advanced GraphRAG system grounded in the
Vietherb OWL/RDF ontology to reduce hallucinations
in Vietnamese medicinal plant question answering.

Target: Q1/Q2 peer-reviewed publication.

## Research priorities
1. Faithful RDF/OWL parsing and graph transformation.
2. Ontology-aware knowledge graph construction.
3. Evidence-grounded hybrid retrieval.
4. Provenance-aware answer generation.
5. Reproducible experiments and ablation studies.

## Technology
Windows 11, Python 3.15, RDFLib 7.6.0,
Neo4j driver 6.4.1, Neo4j Desktop, Git, VS Code.

Project root: D:\vietherb_rag
Neo4j data: D:\Neo4jData

## Current status
- Python, Git, VS Code and virtual environment prepared.
- RDFLib and Neo4j Python driver installed.
- Neo4j DBMS initialization requires verification.
- Real Vietherb OWL parsing requires verification.
- OWL-to-Neo4j starter code is available for review,
  but has not been validated against the real ontology.

## Next milestone
1. Verify Neo4j DBMS and connectivity.
2. Inspect the actual Vietherb OWL file.
3. Analyze classes, properties, individuals and triples.
4. Design and validate RDF-to-Neo4j mapping.
5. Measure transformation integrity and performance.

## Research integrity
No experimental result is accepted without evidence.
No medical claim is considered clinically validated
solely because it exists in the ontology.

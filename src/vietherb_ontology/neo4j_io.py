"""Injected-driver adapter. No connection creation, DDL or credentials here.

Caller must provision constraints and exclusive single-writer ownership before
integration. Phase 1 uses transaction doubles only.
"""
from .pipeline import (IntegrityError, decode_term, triple_record, plan_batches,
                       validate_roundtrip, canonical)

STATE = 'MATCH (s:ImportSnapshot {key:$key}) RETURN properties(s) AS snapshot'
GUARD = '''MATCH (s:ImportSnapshot {key:$key})
MATCH (r:ImportRun {id:$owner})-[:TARGETS]->(s)
WHERE s.state='LOADING' AND s.owner=$owner AND r.status='LOADING'
 AND r.snapshotKey=$key RETURN s.key AS key'''
TERMS = '''UNWIND $rows AS row
MERGE (n:RdfTerm {key:row.key}) ON CREATE SET n += row
RETURN properties(n) AS payload'''
TRIPLES = '''MATCH (snap:ImportSnapshot {key:$key})
WHERE snap.state='LOADING' AND snap.owner=$owner
UNWIND $rows AS row
MATCH (s:RdfTerm {key:row.subjectKey})
MATCH (p:RdfTerm {key:row.predicateKey})
MATCH (o:RdfTerm {key:row.objectKey})
MERGE (t:RdfTriple {key:row.key}) ON CREATE SET t += row
MERGE (t)-[:SUBJECT]->(s)
MERGE (t)-[:PREDICATE]->(p)
MERGE (t)-[:OBJECT]->(o)
MERGE (snap)-[:ASSERTS]->(t)
RETURN properties(t) AS payload'''
EXPORT = '''MATCH (snap:ImportSnapshot {key:$key})-[a:ASSERTS]->(t:RdfTriple)
WITH t, count(a) AS assertionCount
CALL (t) { OPTIONAL MATCH (t)-[r:SUBJECT]->(n)
 RETURN collect(CASE WHEN r IS NOT NULL THEN properties(n) END) AS subjects }
CALL (t) { OPTIONAL MATCH (t)-[r:PREDICATE]->(n)
 RETURN collect(CASE WHEN r IS NOT NULL THEN properties(n) END) AS predicates }
CALL (t) { OPTIONAL MATCH (t)-[r:OBJECT]->(n)
 RETURN collect(CASE WHEN r IS NOT NULL THEN properties(n) END) AS objects }
RETURN properties(t) AS triple, assertionCount, subjects, predicates, objects
ORDER BY triple.key'''


def rows(tx, query, **params):
    return [dict(record) for record in tx.run(query, **params)]


def require_guard(tx, key, owner):
    if rows(tx, GUARD, key=key, owner=owner) != [{'key': key}]:
        raise IntegrityError('Snapshot state/ownership mismatch')


def check_payloads(expected, returned):
    stored = [r['payload'] for r in returned]
    if canonical(sorted(stored,key=lambda r:r['key'])) != canonical(sorted(expected,key=lambda r:r['key'])):
        raise IntegrityError('Payload mismatch or missing MATCH rows')


def write_terms(tx, key, owner, batch):
    require_guard(tx, key, owner)
    for term in batch:
        decode_term(term)
    check_payloads(batch, rows(tx, TERMS, rows=batch))


def write_triples(tx, key, owner, batch):
    require_guard(tx, key, owner)
    for rec in batch:
        if rec != triple_record([rec[k] for k in ('subjectKey','predicateKey','objectKey')]):
            raise IntegrityError('Invalid input triple key')
    check_payloads(batch, rows(tx, TRIPLES, rows=batch, key=key, owner=owner))


def export_snapshot(tx, key, *, allow_loading=False, owner=None):
    snapshots = rows(tx, STATE, key=key)
    if len(snapshots) != 1:
        raise IntegrityError('Missing or duplicate snapshot')
    snap = snapshots[0]['snapshot']
    if snap['state'] != 'VALIDATED':
        if not allow_loading or snap['state'] != 'LOADING' or snap.get('owner') != owner:
            raise IntegrityError('Snapshot is not visible')
    return rows(tx, EXPORT, key=key)


class Neo4jWriter:
    """Lazy facade for the guarded writer (avoids circular low-level imports)."""
    def __new__(cls,driver,*,database,enabled=False):
        from .writer import GuardedWriter
        return GuardedWriter(driver,database=database,enabled=enabled)

"""Review-gated integration runner. Default: offline, no driver construction."""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from .pipeline import BASELINE_SHA256,IntegrityError,export_rows,validate_roundtrip,digest
from .import_plan import build_plan,verify_plan
from .target import TEST_DATABASE,REQUIRED,require_target,inspect_target
from .neo4j_io import Neo4jWriter,export_snapshot


def rollback_probes(driver,database):
    """Real server probes, executed only by the explicitly enabled write mode."""
    from neo4j.exceptions import ConstraintError
    require_target(database)
    evidence=[]
    with driver.session(database=database) as session:
        for name,(label,prop) in REQUIRED.items():
            # Label/property identifiers are from the constant reviewed allowlist.
            marker=digest(['integration-probe',uuid4().hex,name])
            query=f'CREATE (n:{label} {{{prop}:$marker}}) RETURN n.{prop} AS value'
            try:
                with session.begin_transaction() as tx:
                    tx.run(query,marker=marker).consume()
                    try:
                        tx.run(query,marker=marker).consume()
                    except ConstraintError:
                        evidence.append({'probe':name,'constraintRejectedDuplicate':True})
                    else:
                        raise IntegrityError('Constraint probe accepted a duplicate')
                    finally:
                        tx.rollback()
            finally:
                count=session.execute_read(lambda tx:tx.run(
                    f'MATCH (n:{label} {{{prop}:$marker}}) RETURN count(n) AS count',
                    marker=marker).single()['count'])
                if count!=0:
                    raise IntegrityError('Rollback probe left committed records')
        marker=digest(['rollback-sentinel',uuid4().hex])
        with session.begin_transaction() as tx:
            tx.run('CREATE (:RdfTerm {key:$key,kind:"iri",iri:"urn:integration:sentinel"})',key=marker).consume()
            tx.rollback()
        count=session.execute_read(lambda tx:tx.run(
            'MATCH (n:RdfTerm {key:$key}) RETURN count(n) AS count',key=marker).single()['count'])
        if count!=0:
            raise IntegrityError('Sentinel rollback failed')
        evidence.append({'probe':'explicitRollback','passed':True})
    return evidence


def snapshot_counts(tx,key):
    # Count role relationships, including duplicates, scoped to the snapshot.
    query='''MATCH (:ImportSnapshot {key:$key})-[a:ASSERTS]->(t:RdfTriple)
    WITH collect(t) AS triples, count(a) AS assertions
    UNWIND triples AS t
    MATCH (t)-[r:SUBJECT|PREDICATE|OBJECT]->(n)
    RETURN assertions, count(DISTINCT t) AS triples, count(r) AS roleLinks,
           count(DISTINCT n) AS terms'''
    record=tx.run(query,key=key).single()
    if record is None:
        raise IntegrityError('Missing snapshot counts')
    return dict(record)


def integration_suite(driver,plan,database):
    """No teardown/deletes. Successful import/audit records intentionally remain."""
    target=inspect_target(driver,database)
    probes=rollback_probes(driver,database)
    graph,manifest,_,_=verify_plan(plan)
    writer=Neo4jWriter(driver,database=database,enabled=True)
    report=writer.import_plan(plan,run_id='integration-'+uuid4().hex)
    key=manifest['snapshotKey']
    with driver.session(database=database) as session:
        before=session.execute_read(snapshot_counts,key)
    if before!={'assertions':2646,'triples':2646,'roleLinks':7938,'terms':1385}:
        raise IntegrityError('Baseline database counts differ')
    second=writer.import_plan(plan,run_id='integration-'+uuid4().hex)
    with driver.session(database=database) as session:
        after=session.execute_read(snapshot_counts,key)
        if before!=after or not second['passed']:
            raise IntegrityError('Canonical idempotency failed')
        # Corrupt only inside a rolled-back explicit transaction; retain baseline.
        with session.begin_transaction() as tx:
            tx.run('''MATCH (:ImportSnapshot {key:$key})-[:ASSERTS]->(t:RdfTriple)
                WITH t LIMIT 1 MATCH (t)-[:SUBJECT]->(s)
                CREATE (t)-[:SUBJECT]->(s)''',key=key).consume()
            corrupted,_=validate_roundtrip(graph,export_snapshot(tx,key),'VALIDATED')
            tx.rollback()
            if corrupted['passed']:
                raise IntegrityError('Duplicate role link escaped validation')
        restored=session.execute_read(lambda tx:validate_roundtrip(graph,export_snapshot(tx,key),'VALIDATED')[0])
        if not restored['passed']:
            raise IntegrityError('Post-rollback validation failed')
    return {'mode':'integration','databaseOperations':True,'target':target,
            'rollbackProbes':probes,'validation':report,'idempotency':second,
            'counts':after,'duplicateRoleRejected':True,'postRollbackValidation':restored}


def run(argv=None,*,driver_factory=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True)
    parser.add_argument('--source',type=Path,default=Path('VHO.owl'))
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--read-only',action='store_true')
    mode.add_argument('--execute-writes',action='store_true')
    parser.add_argument('--confirm-database')
    parser.add_argument('--exclusive-writer',action='store_true')
    args=parser.parse_args(argv)
    require_target(args.database)
    if args.execute_writes and (args.confirm_database!=TEST_DATABASE or not args.exclusive_writer):
        raise IntegrityError('Writes require exact database confirmation and exclusive writer acknowledgement')
    plan=build_plan(args.source,expected_sha256=BASELINE_SHA256)
    graph,_,terms,triples=verify_plan(plan)
    report,_=validate_roundtrip(graph,export_rows(terms,triples))
    if not report['passed']:
        raise IntegrityError('Offline preflight failed')
    if not args.read_only and not args.execute_writes:
        return {'mode':'offline','connectionOpened':False,'databaseOperations':False,
                'targetDatabase':args.database,'validation':report}
    username,password=os.environ.get('NEO4J_USERNAME'),os.environ.get('NEO4J_PASSWORD')
    if not username or not password:
        raise IntegrityError('Neo4j environment credentials required; never pass them on CLI')
    if driver_factory is None:
        from neo4j import GraphDatabase
        driver_factory=GraphDatabase.driver
    # Fixed local endpoint, never accepts a credential-bearing URI.
    with driver_factory('bolt://127.0.0.1:7687',auth=(username,password),connection_timeout=5) as driver:
        if args.read_only:
            return {'mode':'read-only','databaseOperations':False,
                    'target':inspect_target(driver,args.database),'offlineValidation':report}
        return integration_suite(driver,plan,args.database)


def main():
    try:
        print(json.dumps(run(),ensure_ascii=False,indent=2,default=str))
    except Exception as exc:
        # Do not print driver messages/tracebacks that could contain auth parameters.
        print(json.dumps({'passed':False,'errorType':type(exc).__name__,
                          'detail':'Runner stopped; no automatic cleanup or retry'}))
        raise SystemExit(1) from None


if __name__=='__main__': main()

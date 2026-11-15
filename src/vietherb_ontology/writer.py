"""Guarded single-writer lifecycle, no DDL, credential handling or networking."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import platform
import sys
import subprocess
import rdflib
import neo4j

from .pipeline import IntegrityError,canonical,digest,plan_batches,validate_roundtrip
from .import_plan import verify_plan
from .target import require_target,inspect_target
from .neo4j_io import rows,write_terms,write_triples,export_snapshot

LOOKUP_RUN='''MATCH (r:ImportRun {id:$owner}) OPTIONAL MATCH (r)-[a:TARGETS]->(s)
RETURN properties(r) AS run, collect(s.key) AS targets, count(a) AS targetCount'''
LOOKUP_SOURCE='MATCH (s:SourceArtifact {sha256:$sha}) RETURN properties(s) AS source'
LOOKUP_SNAPSHOT='''MATCH (s:ImportSnapshot {key:$key}) OPTIONAL MATCH (s)-[a:FROM_SOURCE]->(src)
RETURN properties(s) AS snapshot, collect(src.sha256) AS sources, count(a) AS sourceCount'''
INIT='''MERGE (src:SourceArtifact {sha256:$sha}) ON CREATE SET src.byteCount=$byteCount
MERGE (s:ImportSnapshot {key:$key})
ON CREATE SET s.state='LOADING', s.owner=$owner, s.manifestJson=$manifest
MERGE (s)-[:FROM_SOURCE]->(src)
MERGE (r:ImportRun {id:$owner})
ON CREATE SET r.status='LOADING', r.snapshotKey=$key, r.identity=$identity,
 r.metadataJson=$metadata, r.startedUtc=$started
MERGE (r)-[:TARGETS]->(s) RETURN s.key AS key'''
FINISH='''MATCH (r:ImportRun {id:$owner})-[:TARGETS]->(s:ImportSnapshot {key:$key})
WHERE r.identity=$identity AND r.snapshotKey=$key AND r.status='LOADING'
 AND ((s.state='LOADING' AND s.owner=$owner) OR s.state='VALIDATED')
SET s.state='VALIDATED', s.validationJson=$report, r.status='VALIDATED',
 r.validationJson=$report, r.finishedUtc=$finished RETURN s.key AS key'''
FAILED='''MATCH (r:ImportRun {id:$owner})-[:TARGETS]->(s:ImportSnapshot {key:$key})
WHERE r.identity=$identity AND r.snapshotKey=$key AND r.status='LOADING'
SET r.status='FAILED', r.finishedUtc=$finished, r.failureCode=$failure
FOREACH (_ IN CASE WHEN s.state='LOADING' AND s.owner=$owner THEN [1] ELSE [] END |
 SET s.state='FAILED') RETURN s.key AS key'''


def check_identity(tx,*,key,owner,sha,byte_count,manifest,identity):
    sources=rows(tx,LOOKUP_SOURCE,sha=sha)
    if len(sources)>1 or (sources and canonical(sources[0]['source'])!=canonical({'sha256':sha,'byteCount':byte_count})):
        raise IntegrityError('Source payload mismatch')
    snapshots=rows(tx,LOOKUP_SNAPSHOT,key=key)
    if len(snapshots)>1:
        raise IntegrityError('Duplicate snapshot')
    if snapshots:
        row=snapshots[0]; snap=row['snapshot']
        if (snap.get('manifestJson')!=manifest or row['sources']!=[sha]
                or type(row['sourceCount']) is not int or row['sourceCount']!=1 or not sources):
            raise IntegrityError('Snapshot source provenance mismatch')
        if snap.get('state') not in ('LOADING','VALIDATED'):
            raise IntegrityError('Snapshot recovery requires explicit review')
        if snap['state']=='LOADING' and snap.get('owner')!=owner:
            raise IntegrityError('Snapshot already owned')
    runs=rows(tx,LOOKUP_RUN,owner=owner)
    if snapshots and snapshots[0]['snapshot']['state']=='LOADING' and not runs:
        raise IntegrityError('Orphan LOADING snapshot requires explicit recovery review')
    if len(runs)>1:
        raise IntegrityError('Duplicate run')
    if runs:
        row=runs[0]; run=row['run']
        if (run.get('identity')!=identity or run.get('snapshotKey')!=key
                or row['targets']!=[key] or type(row['targetCount']) is not int or row['targetCount']!=1):
            raise IntegrityError('Run identity/target mismatch')
        if run.get('status') not in ('LOADING','VALIDATED'):
            raise IntegrityError('Terminal run; choose a new run ID')
        if not snapshots or (run['status']=='VALIDATED' and snapshots[0]['snapshot']['state']!='VALIDATED'):
            raise IntegrityError('Inconsistent run/snapshot lifecycle')
    return snapshots[0]['snapshot']['state'] if snapshots else None


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def run_metadata(plan,database,target,started):
    root=Path(__file__).resolve().parents[2]
    def git(*args):
        return subprocess.check_output(['git',*args],cwd=root,text=True).strip()
    return {'startedUtc':started,'database':database,'databaseID':str(target['databaseID']),
            'sourcePath':plan.manifest['path'],
            'versions':{'python':sys.version,'rdflib':rdflib.__version__,
                        'driver':neo4j.__version__,'os':platform.platform(),
                        'serverComponents':target['serverComponents']},
            'gitHead':git('rev-parse','HEAD'),'gitDirty':bool(git('status','--porcelain')),
            'settings':{'maxRows':plan.max_rows,'maxBytes':plan.max_bytes,'singleWriter':True},
            'codeHashes':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                         for folder in ('src','tests') for p in sorted((root/folder).rglob('*.py'))}}


class GuardedWriter:
    def __init__(self,driver,*,database,enabled=False):
        require_target(database)
        if type(enabled) is not bool:
            raise IntegrityError('Write enablement must be boolean')
        self.driver,self.database,self.enabled=driver,database,enabled

    def import_plan(self,plan,*,run_id):
        if not self.enabled:
            raise IntegrityError('Database writes disabled')
        if (type(run_id) is not str or not run_id or len(run_id)>128
                or not all(c.isascii() and (c.isalnum() or c in '-_') for c in run_id)):
            raise IntegrityError('Run ID must be a non-secret ASCII identifier')
        graph,manifest,terms,triples=verify_plan(plan)
        batches=[(write_terms,plan_batches(terms,plan.max_rows,plan.max_bytes)),
                 (write_triples,plan_batches(triples,plan.max_rows,plan.max_bytes))]
        target=inspect_target(self.driver,self.database)
        key=manifest['snapshotKey']
        manifest_json=canonical({k:v for k,v in manifest.items() if k!='path'})
        identity=digest([key,self.database,str(target['databaseID']),plan.max_rows,plan.max_bytes])
        started=utc_now(); metadata=canonical(run_metadata(plan,self.database,target,started))
        params={'key':key,'owner':run_id,'sha':manifest['sourceSha256'],
                'byte_count':manifest['byteCount'],'manifest':manifest_json,'identity':identity}
        def initialize(tx):
            state=check_identity(tx,**params)
            result=rows(tx,INIT,key=key,owner=run_id,sha=manifest['sourceSha256'],
                        byteCount=manifest['byteCount'],manifest=manifest_json,
                        identity=identity,metadata=metadata,started=started)
            if result!=[{'key':key}]:
                raise IntegrityError('Initialization row mismatch')
            check_identity(tx,**params)
            return state or 'LOADING'
        with self.driver.session(database=self.database) as session:
            initialized=False
            try:
                state=session.execute_write(initialize)
                initialized=True
                if state=='LOADING':
                    for callback,group in batches:
                        for batch in group:
                            session.execute_write(callback,key,run_id,batch)
                def finish(tx):
                    check_identity(tx,**params)
                    exported=export_snapshot(tx,key,allow_loading=True,owner=run_id)
                    report,_=validate_roundtrip(graph,exported,state)
                    if not report['passed']:
                        raise IntegrityError('Database strict round-trip failed')
                    run=rows(tx,LOOKUP_RUN,owner=run_id)[0]['run']
                    if run['status']!='VALIDATED':
                        if rows(tx,FINISH,key=key,owner=run_id,identity=identity,
                                report=canonical(report),finished=utc_now())!=[{'key':key}]:
                            raise IntegrityError('Publication row mismatch')
                    return report
                return session.execute_write(finish)
            except Exception as original:
                if initialized:
                    try:
                        def fail(tx):
                            check_identity(tx,**params)
                            if rows(tx,FAILED,key=key,owner=run_id,identity=identity,
                                    finished=utc_now(),failure='IMPORT_OR_VALIDATION_FAILED')!=[{'key':key}]:
                                raise IntegrityError('Failure audit row mismatch')
                        session.execute_write(fail)
                    except Exception:
                        original.add_note('Failure audit could not be persisted; original error preserved')
                else:
                    original.add_note('Initialization rolled back or outcome unknown; no failure audit claimed')
                raise

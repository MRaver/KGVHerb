"""Immutable source-byte-backed import plans; verify before opening sessions."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .pipeline import (POLICY, IntegrityError, canonical, digest, parse_bytes,
                       encode_graph, strict_signature, validate_records, plan_batches)


@dataclass(frozen=True)
class ImportPlan:
    source_bytes: bytes
    manifest_json: str
    terms_json: str
    triples_json: str
    max_rows: int = 500
    max_bytes: int = 4 * 1024 * 1024

    @property
    def manifest(self):
        return json.loads(self.manifest_json)


def plan_from_bytes(raw, *, base, source_path='', max_rows=500, max_bytes=4194304):
    if type(raw) is not bytes or type(base) is not str or not base:
        raise IntegrityError('Source bytes and explicit base required')
    graph = parse_bytes(raw, base=base)
    terms, triples = encode_graph(graph)
    sha = hashlib.sha256(raw).hexdigest()
    manifest = {'sourceSha256':sha, 'byteCount':len(raw), 'path':source_path,
                'effectiveBaseIRI':base, 'format':'xml', 'parserPolicy':POLICY,
                'mappingVersion':'term-v1/triple-v1', 'graphScope':'default',
                'normalization':False, 'inference':False, 'importsFetched':False,
                'contentFingerprint':digest(sorted(strict_signature(t) for t in graph))}
    manifest['snapshotKey'] = digest([sha,POLICY,manifest['mappingVersion'],base,'default'])
    plan = ImportPlan(raw,canonical(manifest),canonical(terms),canonical(triples),max_rows,max_bytes)
    validate_records(terms,triples)
    plan_batches(terms,max_rows,max_bytes)
    plan_batches(triples,max_rows,max_bytes)
    return plan


def build_plan(source, *, expected_sha256=None, **settings):
    path = Path(source).resolve()
    raw = path.read_bytes()
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise IntegrityError('Source SHA-256 mismatch')
    return plan_from_bytes(raw,base=path.as_uri(),source_path=str(path),**settings)


def verify_plan(plan):
    if type(plan) is not ImportPlan:
        raise IntegrityError('A byte-backed ImportPlan is required')
    try:
        manifest = plan.manifest
        rebuilt = plan_from_bytes(plan.source_bytes,base=manifest['effectiveBaseIRI'],
                                  source_path=manifest['path'],max_rows=plan.max_rows,max_bytes=plan.max_bytes)
        if (rebuilt.manifest_json,rebuilt.terms_json,rebuilt.triples_json) != (
                plan.manifest_json,plan.terms_json,plan.triples_json):
            raise IntegrityError('Plan/source/manifest identity mismatch')
        terms,triples = json.loads(plan.terms_json),json.loads(plan.triples_json)
        graph = parse_bytes(plan.source_bytes,base=manifest['effectiveBaseIRI'])
        return graph,manifest,terms,triples
    except (KeyError,TypeError,ValueError) as exc:
        raise IntegrityError('Invalid import plan') from exc

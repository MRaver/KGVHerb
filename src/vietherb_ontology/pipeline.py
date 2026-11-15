"""Offline RDF-faithful parsing, codec, planning and strict validation."""
from __future__ import annotations

import hashlib
import json
import threading
import re
from pathlib import Path

import rdflib
from rdflib import BNode, Graph, Literal, URIRef

BASELINE_SHA256 = '2f7083f9fc1758edfadd45bf3b721661c585f1c2d3c750d509d94af78976aa73'
POLICY = 'rdfxml-no-normalize-no-imports-v1'
_PARSE_LOCK = threading.Lock()


class IntegrityError(ValueError):
    """Reject malformed or non-lossless data before publication."""


def require_key(value):
    if type(value) is not str or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise IntegrityError('Invalid SHA-256 key')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def parse_bytes(raw, *, format='xml', base='urn:vietherb:source:'):
    if format not in ('xml', 'turtle', 'nt'):
        raise IntegrityError('Unsupported graph format')
    # Removing NULs also recognizes declarations in UTF-16/32 XML.
    xml_scan = raw.replace(b'\x00', b'').upper()
    if format == 'xml' and (b'<!DOCTYPE' in xml_scan or b'<!ENTITY' in xml_scan):
        raise IntegrityError('DTD/entities are outside parser contract')
    # Serializes all parser calls in this package. External code must not mutate
    # RDFLib global normalization concurrently; CLI runs in its own process.
    with _PARSE_LOCK:
        previous = rdflib.NORMALIZE_LITERALS
        try:
            rdflib.NORMALIZE_LITERALS = False
            graph = Graph().parse(data=raw, format=format, publicID=base)
        finally:
            rdflib.NORMALIZE_LITERALS = previous
    for triple in graph:
        if any(isinstance(term, BNode) for term in triple):
            raise IntegrityError('Blank nodes require a canonicalization policy')
        if not isinstance(triple[0], URIRef) or not isinstance(triple[1], URIRef):
            raise IntegrityError('Invalid subject/predicate role')
    return graph


def parse_source(source, expected_sha256=None):
    path = Path(source).resolve()
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and sha != expected_sha256:
        raise IntegrityError('Source SHA-256 mismatch')
    base = path.as_uri()
    graph = parse_bytes(raw, base=base)
    manifest = {'sourceSha256': sha, 'byteCount': len(raw), 'path': str(path),
                'effectiveBaseIRI': base, 'format': 'xml', 'parserPolicy': POLICY,
                'mappingVersion': 'term-v1/triple-v1', 'graphScope': 'default',
                'normalization': False, 'inference': False, 'importsFetched': False}
    manifest['snapshotKey'] = digest([sha, POLICY, manifest['mappingVersion'], base, 'default'])
    return graph, manifest


def encode_term(term):
    if isinstance(term, URIRef):
        props = {'kind': 'iri', 'iri': str(term)}
        payload = ['iri', str(term)]
    elif isinstance(term, Literal):
        dt = str(term.datatype) if term.datatype is not None else None
        lang = term.language
        props = {'kind': 'literal', 'lexical': str(term), 'datatypePresent': dt is not None,
                 'datatype': dt or '', 'languagePresent': lang is not None, 'language': lang or ''}
        payload = ['literal', str(term), dt, lang]
    else:
        raise IntegrityError('Unsupported RDF term')
    return {'key': digest(['term-v1', payload]), **props}


def decode_term(record):
    try:
        if type(record) is not dict:
            raise IntegrityError('Term must be a dictionary')
        require_key(record['key'])
        if record['kind'] == 'iri':
            fields = {'key', 'kind', 'iri'}
        elif record['kind'] == 'literal':
            fields = {'key','kind','lexical','datatypePresent','datatype','languagePresent','language'}
            for flag in ('datatypePresent','languagePresent'):
                if type(record[flag]) is not bool:
                    raise IntegrityError('Literal flags must be boolean')
        else:
            raise IntegrityError('Unsupported term kind')
        if set(record) != fields or any(type(v) is not str for k,v in record.items()
                                       if k not in ('datatypePresent','languagePresent')):
            raise IntegrityError('Term payload shape/type mismatch')
        if record['kind'] == 'iri':
            term = URIRef(record['iri'])
        elif record['kind'] == 'literal':
            dt = URIRef(record['datatype']) if record['datatypePresent'] else None
            lang = record['language'] if record['languagePresent'] else None
            if dt is not None and lang is not None:
                raise IntegrityError('Literal has both datatype and language')
            term = Literal(record['lexical'], datatype=dt, lang=lang, normalize=False)
        else:
            raise IntegrityError('Unsupported term kind')
        if encode_term(term) != record:
            raise IntegrityError('Term payload/key mismatch')
        return term
    except (KeyError, TypeError, ValueError) as exc:
        raise IntegrityError('Incomplete term payload') from exc


def triple_record(keys):
    if len(keys) != 3:
        raise IntegrityError('Triple requires three endpoint keys')
    for key in keys:
        require_key(key)
    return dict(zip(('key', 'subjectKey', 'predicateKey', 'objectKey'),
                    (digest(['triple-v1', *keys]), *keys)))


def encode_graph(graph):
    terms, triples = {}, {}
    for triple in graph:
        keys = []
        if not isinstance(triple[0], URIRef) or not isinstance(triple[1], URIRef):
            raise IntegrityError('Invalid triple roles')
        for term in triple:
            rec = encode_term(term)
            if rec['key'] in terms and terms[rec['key']] != rec:
                raise IntegrityError('Term collision')
            terms[rec['key']] = rec
            keys.append(rec['key'])
        rec = triple_record(keys)
        if rec['key'] in triples and triples[rec['key']] != rec:
            raise IntegrityError('Triple collision')
        triples[rec['key']] = rec
    return sorted(terms.values(), key=lambda r: r['key']), sorted(triples.values(), key=lambda r: r['key'])


def plan_batches(records, max_rows=500, max_bytes=4 * 1024 * 1024):
    if type(max_rows) is not int or type(max_bytes) is not int or max_rows <= 0 or max_bytes < 2:
        raise ValueError('Invalid batch limits')
    records = sorted(records, key=lambda r: r['key'])
    if len({r['key'] for r in records}) != len(records):
        raise IntegrityError('Duplicate input keys')
    batches, batch = [], []
    for record in records:
        if len(canonical([record]).encode('utf-8')) > max_bytes:
            raise IntegrityError('Single row exceeds batch byte limit')
        if batch and (len(batch) == max_rows or len(canonical(batch + [record]).encode('utf-8')) > max_bytes):
            batches.append(batch)
            batch = []
        batch.append(record)
    if batch:
        batches.append(batch)
    return batches


def export_rows(terms, triples):
    """Build the same lossless structural envelope used by the DB exporter."""
    validate_records(terms, triples)
    lookup = {r['key']: r for r in terms}
    return [{'triple': t, 'assertionCount': 1,
             'subjects': [lookup[t['subjectKey']]], 'predicates': [lookup[t['predicateKey']]],
             'objects': [lookup[t['objectKey']]]} for t in triples]


def strict_signature(triple):
    # Independent of hash codec: exact RDF lexical/datatype/language tuples.
    def signature(term):
        if isinstance(term, URIRef):
            return ('iri', str(term))
        if isinstance(term, Literal):
            return ('literal', str(term), str(term.datatype) if term.datatype else None, term.language)
        raise IntegrityError('Unsupported reference term')
    return canonical([signature(t) for t in triple])


def validate_roundtrip(expected, rows, state='LOADING'):
    if state not in ('LOADING', 'VALIDATED'):
        raise IntegrityError('Snapshot not exportable for validation')
    reference = {strict_signature(t) for t in expected}
    actual, keys, errors = set(), set(), []
    decoded = Graph()
    for row in rows:
        try:
            rec = row['triple']
            if rec['key'] in keys:
                raise IntegrityError('Duplicate assertion/triple row')
            keys.add(rec['key'])
            if (type(row['assertionCount']) is not int or row['assertionCount'] != 1
                    or any(type(row[role]) is not list or len(row[role]) != 1
                           for role in ('subjects', 'predicates', 'objects'))):
                raise IntegrityError('Triple role/assertion cardinality mismatch')
            terms = [decode_term(row[role][0]) for role in ('subjects', 'predicates', 'objects')]
            if not isinstance(terms[0], URIRef) or not isinstance(terms[1], URIRef):
                raise IntegrityError('Invalid subject/predicate kind')
            expected_record = triple_record([row[role][0]['key'] for role in ('subjects', 'predicates', 'objects')])
            if rec != expected_record:
                raise IntegrityError('Triple payload/key mismatch')
            actual.add(strict_signature(terms))
            decoded.add(tuple(terms))
        except (IntegrityError, KeyError, TypeError) as exc:
            errors.append(str(exc))
    missing, extra = sorted(reference - actual), sorted(actual - reference)
    return {'passed': not missing and not extra and not errors and len(rows) == len(reference),
            'expectedTriples': len(reference), 'exportRows': len(rows), 'decodedTriples': len(actual),
            'missing': len(missing), 'extra': len(extra), 'mismatch': len(errors),
            'errors': errors, 'missingRecords': missing, 'extraRecords': extra,
            'fingerprint': digest(sorted(actual))}, decoded


def validate_records(terms, triples):
    """Validate the complete plan, including unused and duplicate terms."""
    lookup = {}
    for rec in terms:
        term = decode_term(rec)
        if rec['key'] in lookup:
            raise IntegrityError('Duplicate term key')
        lookup[rec['key']] = term
    seen, used = set(), set()
    for rec in triples:
        try:
            keys = [rec[k] for k in ('subjectKey','predicateKey','objectKey')]
            if rec != triple_record(keys) or rec['key'] in seen:
                raise IntegrityError('Duplicate or malformed triple')
            seen.add(rec['key'])
            if not isinstance(lookup[keys[0]], URIRef) or not isinstance(lookup[keys[1]], URIRef):
                raise IntegrityError('Invalid triple roles')
            for key in keys:
                if key not in lookup:
                    raise IntegrityError('Missing endpoint')
            used.update(keys)
        except (KeyError, TypeError) as exc:
            raise IntegrityError('Missing or malformed endpoint') from exc
    if used != set(lookup):
        raise IntegrityError('Unused terms in import plan')

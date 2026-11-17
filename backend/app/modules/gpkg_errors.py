"""Structured import diagnostics. No source values, secrets or invented defaults."""
import re,sqlite3
from pymongo.errors import (PyMongoError,ConnectionFailure,OperationFailure,DuplicateKeyError)
from .qgis_data import ApiError

def issue(stage,reason,*,severity='critical',row=None,field=None,code='import_error',retryable=False,source_key=None):
    return {'severity':severity,'stage':stage,'row':row,'field':field,'code':code,
            'reason':str(reason)[:1500],'retryable':bool(retryable),'source_key':source_key}
class ImportFailure(ApiError):
    def __init__(self,status,diagnostic):
        super().__init__(status,diagnostic['reason']);self.issue=diagnostic

def fail(stage,reason,field=None,code='invalid_structure',status=422,retryable=False):
    raise ImportFailure(status,issue(stage,reason,field=field,code=code,retryable=retryable))

def classify(exc,stage,row=None,field=None,source_key=None):
    if isinstance(exc,ImportFailure):
        result=dict(exc.issue);result.update(stage=stage if row else result['stage'],row=row,source_key=source_key)
        return result
    status=getattr(exc,'status',None);text=str(exc)
    if isinstance(exc,ConnectionFailure):
        return issue(stage,'MongoDB connection unavailable; import stopped, retry after recovery',row=row,field=field,code='mongodb_unavailable',retryable=True,source_key=source_key)
    if isinstance(exc,OperationFailure) and exc.code in (13,18):
        return issue(stage,'MongoDB authentication or write privileges are insufficient',row=row,field=field,code='mongodb_forbidden',source_key=source_key)
    if isinstance(exc,PyMongoError) and not isinstance(exc,DuplicateKeyError) and getattr(exc,'code',None)!=121:
        return issue(stage,'MongoDB operation failed; no row is skipped, retry after recovery',row=row,field=field,code='mongodb_operation',retryable=True,source_key=source_key)
    if isinstance(exc,(sqlite3.DatabaseError,OSError)):
        return issue(stage,'File/staging storage error: '+text,row=row,field=field,code='storage_error',retryable=isinstance(exc,OSError) or 'locked' in text.lower(),source_key=source_key)
    if status in (401,403):return issue(stage,text,row=row,field=field,code='forbidden',source_key=source_key)
    if status==503:return issue(stage,text,row=row,field=field,code='service_unavailable',retryable=True,source_key=source_key)
    if field is None:
        match=re.search(r'\b(?:Geodata|Patient|Instances|Therapy|Region|Municipality|Settlement|Street|Building|Location|Foci|Gender|Severity|Influence|Social_group|Reception|Placement)\.[\w.]+',text)
        if match:field=match.group(0).rstrip('.')
    code='invalid_value'
    if 'required' in text.lower():code='required_value'
    elif 'target missing' in text or 'conflict' in text.lower():code='foreign_key' if 'target' in text or 'Therapy.patient' in text else 'conflict'
    elif 'geometry' in text.lower() or 'coordinate' in text.lower() or field=='Geodata.geometry':code='invalid_geometry'
    elif isinstance(exc,DuplicateKeyError):code='duplicate_conflict'
    severity='error' if row is not None and (isinstance(exc,(ApiError,ValueError,TypeError,OverflowError,DuplicateKeyError)) or getattr(exc,'code',None)==121) else 'critical'
    return issue(stage,text,severity=severity,row=row,field=field,code=code,source_key=source_key)

"""Run prepare/partial/finish on separate backend processes and the same disk."""
import sys,json,tempfile,sqlite3
from pathlib import Path
from comprehensive_http import call,console
from gpkg_fixture import build
phase,checkpoint=sys.argv[1:];checkpoint=Path(checkpoint)
if phase=='prepare':
    with tempfile.TemporaryDirectory() as folder:
        source=Path(folder)/'restart.gpkg';build(source)
        db=sqlite3.connect(source);row=db.execute('SELECT * FROM cases_points LIMIT 1').fetchone();db.execute('DELETE FROM cases_points')
        db.executemany('INSERT INTO cases_points VALUES(?,?,?,?,?,?,?,?)',[(i,*row[1:]) for i in range(1,1004)]);db.commit();db.close()
        upload=call('POST','/v1/gpkg/upload',source.read_bytes())
    state=call('POST','/v1/gpkg/jobs',{'upload_id':upload['upload_id'],'table':'cases_points','mapping':{},'use_geometry':True})
    before=console('db.Geodata.countDocuments({})')['value'];state=call('POST','/v1/gpkg/jobs/'+state['job_id']+'/validate',{})
    assert state['checked']==250 and state['status']=='validating'
    checkpoint.write_text(json.dumps({'job_id':state['job_id'],'before':before}));print('PASS checkpoint after first validation page',flush=True)
else:
    saved=json.loads(checkpoint.read_text());identifier=saved['job_id'];state=call('GET','/v1/gpkg/jobs/'+identifier)
    if phase=='partial':
        assert state['checked']==250 and state['applied']==0
        while state['status']=='validating':state=call('POST','/v1/gpkg/jobs/'+identifier+'/validate',{})
        assert state['status']=='ready' and state['checked']==1003
        state=call('POST','/v1/gpkg/jobs/'+identifier+'/apply',{})
        assert state['applied']==25 and console('db.Geodata.countDocuments({})')['value']==saved['before']+25
        print('PASS validation state survived actual backend restart; first 25 rows imported',flush=True)
    else:
        assert state['applied']==25
        while state['status']!='complete':state=call('POST','/v1/gpkg/jobs/'+identifier+'/apply',{})
        assert state['applied']==1003 and console('db.Geodata.countDocuments({})')['value']==saved['before']+1003
        call('POST','/v1/gpkg/jobs/'+identifier+'/apply',{})
        assert console('db.Geodata.countDocuments({})')['value']==saved['before']+1003
        print('PASS import state survived second backend restart; all 1003 rows exactly once',flush=True)

load('/opt/storage/admin.js');
const a=db.getSiblingDB('admin');
try { const status=a.runCommand({replSetGetStatus:1}); if(!status.ok) throw status; }
catch(e) {
  if(e.code!==94) throw e;
  const result=a.runCommand({replSetInitiate:{_id:'rs0',members:[{_id:0,host:'storage:27017'}]}});
  if(!result.ok) throw new Error('Replica set initialization failed');
}
let primary=false;
for(let i=0;i<120;i++) {
  if(a.runCommand({hello:1}).isWritablePrimary) {primary=true;break;}
  sleep(500);
}
if(!primary) throw new Error('Primary election timeout');
print('PASS replica set primary');

// Availability only: no password, schema or user lookup. Final mongod only.
try {
  const fs=require('fs');
  if(fs.readFileSync('/proc/1/comm','utf8').trim()!=='mongod') quit(1);
  const c=new Mongo('mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=2000&connectTimeoutMS=2000');
  if(c.getDB('admin').runCommand({ping:1}).ok!==1) quit(1);
} catch (_) {print('WAIT final mongod unavailable');quit(1);}

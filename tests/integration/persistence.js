try {
  load('/opt/storage/admin.js');
  if(db.cases.countDocuments({source:'integration-test'})!==1) throw new Error('Record did not persist');
  print('PASS data survived container restart');
} catch (_) {print('FAIL persistence');quit(1);}

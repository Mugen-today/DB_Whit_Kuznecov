// Only this file is in /docker-entrypoint-initdb.d; load order is explicit.
for (const name of ['schema','roles','indexes']) load('/opt/init/'+name+'.js');
print('PASS Storage bootstrap');

try {
 load('/opt/storage/replica.js');
 load('/opt/init/schema.js');
 load('/opt/init/roles.js');
 load('/opt/init/indexes.js');
 load('/opt/storage/geospatial-index.js');
} catch (e) { print('FAIL provisioning: '+e.message); quit(1); }

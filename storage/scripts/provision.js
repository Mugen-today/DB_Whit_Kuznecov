try { load('/opt/storage/admin.js'); load('/opt/init/roles.js'); }
catch (_) { print('FAIL role provisioning; check admin credentials and permissions'); quit(1); }

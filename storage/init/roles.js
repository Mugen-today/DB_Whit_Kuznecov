(() => {
  load('/opt/storage/role-spec.js');
  const spec=JSON.parse(require('fs').readFileSync('/opt/schema/model.json','utf8'));
  const s=db.getSiblingDB('Schema');
  // Check all configuration BEFORE any change.
  for(const [,key] of accountSpec())if(!process.env[key])throw new Error('Missing '+key+'; run manage.py configure');
  for(const [name,definition] of Object.entries(roleSpec(spec))) {
    const target=db.getSiblingDB(roleDatabase(name));
    if(target.getRole(name))target.updateRole(name,definition);else target.createRole({role:name,...definition});
  }
  for(const [user,key,role] of accountSpec()) {
    const roles=[{role,db:'Schema'}];
    if(s.getUser(user))s.updateUser(user,{roles});else s.createUser({user,pwd:process.env[key],roles});
  }
  // storage_admin already has root in admin from image initialization.
  // gis_admin is an explicit assignable admin role, not a new default root password.
  print('PASS technical accounts and gis_admin/gis_user/gis_guest roles; existing passwords retained');
})();

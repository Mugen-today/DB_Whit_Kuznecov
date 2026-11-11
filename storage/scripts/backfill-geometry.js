// Explicit, repeatable conversion. Invalid or conflicting documents are not overwritten.
load('/opt/storage/admin.js');
const c=db.getSiblingDB('Schema').Geodata;
const filter={geometry:{$exists:false},Longitude:{$type:'number',$gte:-180,$lte:180},Latitude:{$type:'number',$gte:-90,$lte:90}};
const result=c.updateMany(filter,[{$set:{geometry:{type:'Point',coordinates:['$Longitude','$Latitude']}}}]);
print('geometry added: '+result.modifiedCount);

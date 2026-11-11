// Non-destructive index preparation: keep invalid rows, index only validated points.
load('/opt/storage/admin.js');
(() => {
 const c=db.getSiblingDB('Schema').Geodata;
 let ops=[],valid=0,invalid=0;
 const number=x=>x!==null && x!==undefined && typeof x!=='boolean' && !(typeof x==='string'&&!x.trim()) && Number.isFinite(Number(x));
 const coords=(x,y)=>number(x)&&number(y)&&Number(x)>=-180&&Number(x)<=180&&Number(y)>=-90&&Number(y)<=90;
 function flush(){if(ops.length){c.bulkWrite(ops,{ordered:false});ops=[];}}
 c.find({}, {_id:1,geometry:1,Longitude:1,Latitude:1,_geometry_valid:1,_previous_geometry:1}).forEach(d=>{
   let g=d.geometry;
   const fields={};
   const empty=g===undefined || g===null || g==='' || (Array.isArray(g)&&g.length===0) || (typeof g==='object'&&!Array.isArray(g)&&(Object.keys(g).length===0 || (g.type==='Point'&&(!g.coordinates || (Array.isArray(g.coordinates)&&g.coordinates.length===0)))));
   if(empty && coords(d.Longitude,d.Latitude)) {
     if(d.geometry!==undefined && d._previous_geometry===undefined) fields._previous_geometry=d.geometry;
     g={type:'Point',coordinates:[Number(d.Longitude),Number(d.Latitude)]};
     fields.geometry=g;
   }
   let ok=!!g && g.type==='Point' && Array.isArray(g.coordinates) && g.coordinates.length===2 && coords(...g.coordinates);
   if(ok && d.Longitude!==undefined && d.Latitude!==undefined)
     ok=coords(d.Longitude,d.Latitude)&&Math.abs(Number(d.Longitude)-Number(g.coordinates[0]))<1e-8&&Math.abs(Number(d.Latitude)-Number(g.coordinates[1]))<1e-8;
   if(ok)valid++;else invalid++;
   if(d._geometry_valid!==ok)fields._geometry_valid=ok;
   if(Object.keys(fields).length)ops.push({updateOne:{filter:{_id:d._id},update:{$set:fields}}});
   if(ops.length>=500)flush();
 });
 flush();
 c.createIndex({geometry:'2dsphere'},{name:'gis_valid_geometry',partialFilterExpression:{_geometry_valid:true}});
 print('PASS spatial index; valid='+valid+'; invalid preserved='+invalid);
})();

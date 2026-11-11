(async () => {
// Curated read-only catalog only, not a general eval API.
const fs=require('fs');
const catalog=JSON.parse(fs.readFileSync(process.env.QUERY_CATALOG,'utf8'));
const AS_OF=new Date(process.env.QUERY_AS_OF||'2026-11-10T00:00:00Z');
const out=[];
for(const q of catalog) {
  const started=Date.now();
  try {
    let plan={};
    const proxy=new Proxy({}, {get:(_,collection)=>new Proxy({}, {get:(_,method)=>(...args)=>{
      plan={collection,method,args};
      const chain={sort(value){plan.sort=value;return chain;},limit(value){plan.limit=value;return chain;},count(){plan.count=true;return chain;}};
      return chain;
    }})});
    new Function('db','AS_OF','return '+q.mongo)(proxy,AS_OF);
    let result=await db.getCollection(plan.collection)[plan.method](...plan.args);
    if(plan.sort) result=result.sort(plan.sort);
    if(plan.limit) result=result.limit(plan.limit);
    if(plan.count) result=await result.count();
    const rows=result && typeof result.toArray==='function'?await result.toArray():result;
    out.push({number:q.number,ok:true,elapsed_ms:Date.now()-started,plan,result:rows});
  }catch(e){out.push({number:q.number,ok:false,error:e.message});}
}
fs.writeFileSync(process.env.QUERY_OUTPUT,EJSON.stringify({as_of:AS_OF,queries:out},null,2,{relaxed:false}));
print('Executed '+out.length+'; errors '+out.filter(q=>!q.ok).length);

})()

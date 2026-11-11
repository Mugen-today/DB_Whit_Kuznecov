"""Server-side WGS84 Point normalisation; never invent missing coordinates."""
import math
from .qgis_data import ApiError

def normalize(data):
    result=dict(data)
    geometry=result.get('geometry')
    if geometry is not None:
        if not isinstance(geometry,dict) or set(geometry)!={'type','coordinates'} or geometry['type']!='Point':
            raise ApiError(422,'geometry must be GeoJSON Point')
        coords=geometry['coordinates']
        if not isinstance(coords,list) or len(coords)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in coords):
            raise ApiError(422,'Point requires two finite coordinates')
        for key,value in zip(('Longitude','Latitude'),coords):
            if key in result and result[key]!=value: raise ApiError(422,'geometry conflicts with Longitude/Latitude')
            result[key]=float(value)
    if 'Longitude' in result and 'Latitude' in result:
        lon,lat=result['Longitude'],result['Latitude']
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (lon,lat)) or not -180<=lon<=180 or not -90<=lat<=90:
            raise ApiError(422,'Invalid WGS84 coordinates')
        result['geometry']={'type':'Point','coordinates':[float(lon),float(lat)]}
    return result

def read_geometry(doc):
    """Tolerant historical read adapter. Strict normalize still governs all writes."""
    import json
    def number(value):
        if isinstance(value,dict):
            for tag in ('$numberDecimal','$numberDouble','$numberLong','$numberInt'):
                if tag in value:return float(value[tag])
        if isinstance(value,bool):raise ValueError('Boolean coordinate')
        if hasattr(value,'to_decimal'):value=value.to_decimal()
        return float(value)
    def point(values):
        if not isinstance(values,(list,tuple)) or len(values)!=2:raise ValueError('Expected a 2D Point')
        x,y=map(number,values)
        if not all(math.isfinite(v) for v in (x,y)):raise ValueError('Nonfinite coordinate')
        return x,y
    raw=doc.get('geometry');warning=None
    if raw is not None:
        try:
            geometry=json.loads(raw) if isinstance(raw,str) else raw
            if not isinstance(geometry,dict) or geometry.get('type')!='Point':raise ValueError('Expected GeoJSON Point')
            x,y=point(geometry.get('coordinates'))
            crs=geometry.get('crs')
            if crs:
                if not isinstance(crs,dict) or crs.get('type')!='name':raise ValueError('Unknown geometry CRS')
                source=crs.get('properties',{}).get('name')
                if not source:raise ValueError('Missing geometry CRS')
                from pyproj import Transformer
                x,y=Transformer.from_crs(source,'EPSG:4326',always_xy=True,allow_ballpark=False).transform(x,y,errcheck=True)
            geometry=normalize({'Longitude':x,'Latitude':y})['geometry']
            if 'Longitude' in doc and 'Latitude' in doc:
                try:
                    a,b=point([doc['Longitude'],doc['Latitude']])
                    if abs(a-x)>1e-8 or abs(b-y)>1e-8:warning='geometry and coordinate attributes differ; geometry displayed'
                except (ValueError,TypeError):warning='Invalid coordinate attributes; geometry displayed'
            return geometry,warning
        except Exception as exc:warning='Invalid stored geometry: '+str(exc)[:200]
    try:
        x,y=point([doc.get('Longitude'),doc.get('Latitude')])
        return normalize({'Longitude':x,'Latitude':y})['geometry'],warning
    except (ValueError,TypeError,OverflowError,ApiError):
        return None,warning or 'No valid WGS84 Point or coordinate pair; row retained without geometry'

def features(records):
    result=[]
    for d in records:
        geometry,warning=read_geometry(d)
        item={'type':'Feature','id':d.get('_key',d['_id']),'properties':{'mongo_id':d['_id']},'geometry':geometry}
        if geometry:
            x,y=geometry['coordinates'];item['geometry_wkt']='POINT ('+format(x,'.17g')+' '+format(y,'.17g')+')'
        if warning:item['geometry_warning']=warning
        result.append(item)
    return result

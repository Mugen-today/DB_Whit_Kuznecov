"""Minimal conforming 2D Point GeoPackage in EPSG:3857, with mapped clinical fields."""
import sqlite3,struct,math
def build(path,invalid=False):
    c=sqlite3.connect(path)
    c.executescript("""
PRAGMA application_id=1196444487;
CREATE TABLE gpkg_spatial_ref_sys(srs_name TEXT NOT NULL,srs_id INTEGER PRIMARY KEY,organization TEXT NOT NULL,organization_coordsys_id INTEGER NOT NULL,definition TEXT NOT NULL,description TEXT);
INSERT INTO gpkg_spatial_ref_sys VALUES('WGS 84 / Pseudo-Mercator',3857,'EPSG',3857,'EPSG:3857',NULL);
CREATE TABLE gpkg_contents(table_name TEXT PRIMARY KEY,data_type TEXT NOT NULL,identifier TEXT UNIQUE,description TEXT DEFAULT '',last_change DATETIME NOT NULL DEFAULT '2026-11-10T00:00:00Z',min_x DOUBLE,min_y DOUBLE,max_x DOUBLE,max_y DOUBLE,srs_id INTEGER);
INSERT INTO gpkg_contents(table_name,data_type,identifier,srs_id) VALUES('cases_points','features','cases_points',3857);
CREATE TABLE gpkg_geometry_columns(table_name TEXT NOT NULL,column_name TEXT NOT NULL,geometry_type_name TEXT NOT NULL,srs_id INTEGER NOT NULL,z TINYINT NOT NULL,m TINYINT NOT NULL,PRIMARY KEY(table_name,column_name));
INSERT INTO gpkg_geometry_columns VALUES('cases_points','geom','POINT',3857,0,0);
CREATE TABLE cases_points(fid INTEGER PRIMARY KEY,geom POINT,passport TEXT,age INTEGER,registered TEXT,started TEXT,diagnosis TEXT,event_date TEXT);
""")
    x=6378137*math.radians(30);y=6378137*math.log(math.tan(math.pi/4+math.radians(60)/2))
    blob=b'GP'+bytes([0,1])+struct.pack('<i',3857)+struct.pack('<BI2d',1,1,x,y)
    for i in (1,2):
        c.execute('INSERT INTO cases_points VALUES(?,?,?,?,?,?,?,?)',(i,blob,'TEST%03d'%i,None if invalid and i==2 else 25,'2026-11-10','2026-11-10','["TEST"]','2026-11-10'))
    c.commit();c.close()
MAPPING={'Patient.passport':'passport','Patient.age':'age','Patient.reg_date':'registered','Instances.date':'event_date','Therapy.date_start':'started','Therapy.diagnosis':'diagnosis'}

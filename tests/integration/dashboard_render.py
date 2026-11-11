"""Streamlit's actual script runner, backed by the live authenticated backend."""
import os,sys
from pathlib import Path
from streamlit.testing.v1 import AppTest
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'dashboard'))
os.environ['BACKEND_URL']=os.environ['QGIS_TEST_BACKEND']
for role in ('reader','user','guest'):
    app=AppTest.from_file(str(root/'dashboard/app.py'),default_timeout=90)
    app.session_state['auth_role']=role
    app.run(timeout=90)
    assert not app.exception,[e.message for e in app.exception]
    assert not app.error,[e.value for e in app.error]
    assert len(app.tabs)==4
    if role=='reader':
        from comprehensive_http import console
        expected=console('db.Instances.countDocuments({})','reader')['value']
        assert any('все загруженные обращения: '+str(expected) in c.value for c in app.caption),[(c.value) for c in app.caption]
        mode=next(w for w in app.radio if "Консоль запросов через backend для аналитика" in w.options)
        mode.set_value("Консоль запросов через backend для аналитика").run(timeout=90)
        button=next(w for w in app.button if w.label=="Выполнить запрос и вывести в таблицу")
        button.click().run(timeout=90)
        assert not app.exception and not app.error
        fmt=next(w for w in app.radio if w.label=="Формат разметки")
        fmt.set_value("XML").run(timeout=90)
        next(w for w in app.button if w.label=="Выполнить запрос и вывести в таблицу").click().run(timeout=90)
        assert not app.exception and not app.error
        print('PASS dashboard JSON/XML console through authenticated backend',flush=True)
    print('PASS Streamlit tabs, filters, charts and journal role',role,flush=True)

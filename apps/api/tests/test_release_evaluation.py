import json
from PIL import Image
from app.extraction_benchmark import image_identity
from scripts.evaluate_release import evaluate
import pytest

def corpus(tmp_path,count):
    cases=[]
    for i in range(count):
        im=tmp_path/f'{i}.png';Image.new('RGB',(100,100),(i*10,0,0)).save(im)
        pts=[(10,10),(90,10),(90,90),(10,90),(10,10)]
        prediction={'provider':'fixture','walls':[{'start':dict(x=a[0],y=a[1]),'end':dict(x=b[0],y=b[1])} for a,b in zip(pts,pts[1:])],**image_identity(im)}
        path=tmp_path/f'{i}.json';path.write_text(json.dumps(prediction))
        cases.append(dict(image=im.name,truth=path.name,prediction=path.name,group_id=str(i),independently_reviewed=True,exterior_complete=True,opening_spans_reviewed=True,correction_seconds=120))
    manifest=tmp_path/'release.json';manifest.write_text(json.dumps(dict(split='test',frozen=True,cases=cases)));return manifest

def test_release_refuses_small_corpus_even_when_perfect(tmp_path):
    assert not evaluate(corpus(tmp_path,1))['passed']

def test_release_requires_quality_and_measured_correction_time(tmp_path):
    path=corpus(tmp_path,10);assert evaluate(path)['passed']
    doc=json.loads(path.read_text());doc['cases'][0]['exterior_complete']=False;path.write_text(json.dumps(doc))
    assert not evaluate(path)['passed']
    doc['cases'][0]['correction_seconds']=float('nan');path.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='correction_seconds'):evaluate(path)

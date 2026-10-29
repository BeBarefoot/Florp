import json
import pytest
from PIL import Image
from app.training_dataset import prepare,verify_dataset,digest
from scripts.train_segmentation import training_options


def manifest(tmp_path):
    cases=[]
    for i,split in enumerate(['train','val','test']):
        image=tmp_path/f'{i}.png';Image.new('RGB',(64,32),(i*50,0,0)).save(image)
        annotation=tmp_path/f'{i}.json'
        annotation.write_text(json.dumps({'width_px':64,'height_px':32,'independently_reviewed':True,
            'annotation_complete':True,'reviewer':'reviewer-1','objects':[
                {'kind':'wall','polygon':[[2,2],[60,2],[60,5],[2,5]]}]}))
        cases.append({'id':f'plan-{i}','group_id':f'building-{i}','split':split,'image':image.name,
            'annotation':annotation.name,'source_sha256':digest(image),'usage_rights_confirmed':True})
    path=tmp_path/'manifest.json';path.write_text(json.dumps({'cases':cases}));return path,cases


def test_prepare_and_verify_source_bound_normalized_masks(tmp_path):
    path,cases=manifest(tmp_path);out=tmp_path/'dataset'
    report=prepare(path,out)
    assert len(report['cases'])==3
    assert verify_dataset(out)==report
    tokens=(out/'labels/train/plan-0.txt').read_text().split()
    assert tokens[0]=='0' and float(tokens[1])==pytest.approx(2/64)
    assert all(0<=float(v)<=1 for v in tokens[1:])
    with pytest.raises(ValueError,match='already exists'):prepare(path,out)
    (out/'labels/train/plan-0.txt').write_text('tampered')
    with pytest.raises(ValueError,match='changed'):verify_dataset(out)

@pytest.mark.parametrize('problem',['group','hash','duplicate','unreviewed','bounds','dimension'])
def test_bad_datasets_leave_no_partial_output(tmp_path,problem):
    path,cases=manifest(tmp_path)
    if problem=='group':cases[1]['group_id']=cases[0]['group_id']
    elif problem=='hash':cases[0]['source_sha256']='a'*64
    elif problem=='duplicate':cases[1].update(image=cases[0]['image'],source_sha256=cases[0]['source_sha256'])
    else:
        ann=tmp_path/'0.json';data=json.loads(ann.read_text())
        if problem=='unreviewed':data['independently_reviewed']=False
        if problem=='bounds':data['objects'][0]['polygon'][0]=[-1,2]
        if problem=='dimension':data['width_px']=65
        ann.write_text(json.dumps(data))
    path.write_text(json.dumps({'cases':cases}))
    with pytest.raises(ValueError):prepare(path,tmp_path/'dataset')
    assert not (tmp_path/'dataset').exists()


def test_training_options_pin_data_seed_and_do_not_touch_test_split(tmp_path):
    path,_=manifest(tmp_path);out=tmp_path/'dataset';prepare(path,out)
    checkpoint=tmp_path/'trusted.pt';checkpoint.write_bytes(b'test fixture, not real weights')
    options=training_options(out,checkpoint,tmp_path/'run',2,128,1,'cpu',42)
    assert options['seed']==42 and options['deterministic'] and options['workers']==0
    assert options['task']=='segment' and 'split' not in options
    assert options['mosaic']==0 and options['fliplr']==0

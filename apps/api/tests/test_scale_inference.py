from app.scale_inference import automatic_scale
from app.measurements import ScaleSuggestion

def candidate(px, text, x):
    return ScaleSuggestion(text=text,source='pdf_text',confidence=.42,
        dimension_m=5,pixels=px*5,px_per_meter=px,
        line={'x1':x,'y1':0,'x2':x+10,'y2':0})
def test_single_measurement_does_not_set_scale():
    assert automatic_scale([candidate(40,'500',0)]) is None
def test_disagreement_does_not_set_scale():
    assert automatic_scale([candidate(40,'500',0),candidate(75,'600',40),candidate(110,'700',80)]) is None
def test_consensus_is_provisional():
    v=automatic_scale([candidate(40,'500',0),candidate(41,'600',40),candidate(39.7,'700',80)])
    assert v is not None
    assert v.status=='provisional_auto'
    assert 39<v.px_per_meter<42

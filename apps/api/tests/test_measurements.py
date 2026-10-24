from app.measurements import scale_suggestions
from app.evidence import Segment, TextEvidence
from app.geometry import Geometry,Room,Pt,Opening
def test_scale_suggestion_requires_matching_line():
    labels=[TextEvidence(text='500',bbox=[180,70,220,90],source='pdf_text',confidence=.9)]
    assert not scale_suggestions([],labels,800,600)
    seg=[Segment(x1=100,y1=110,x2=600,y2=110,source='pdf_vector',confidence=.9)]
    result=scale_suggestions(seg,labels,800,600)
    assert result and result[0].dimension_m==5
    assert result[0].confidence<.5
def test_dimension_not_silently_confirmed():
    assert scale_suggestions([],[],800,600)==[]

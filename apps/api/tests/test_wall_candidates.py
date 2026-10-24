from app.evidence import Segment, TextEvidence
from app.wall_candidates import wall_candidates

def seg(a,b,c,d):
    return Segment(x1=a,y1=b,x2=c,y2=d,source='raster_hough',confidence=.7)

def test_parallel_wall_candidate():
    c=wall_candidates([seg(100,100,500,100),seg(100,110,500,110)],[],900,600)
    assert len(c)==1 and c[0].y1==105

def test_single_line_not_a_wall():
    assert wall_candidates([seg(20,50,490,50)],[],900,600)==[]

def test_short_furniture_lines_rejected():
    assert wall_candidates([seg(50,50,75,50),seg(50,57,75,57)],[],900,600)==[]

def test_text_midpoint_filters_candidate():
    labels=[TextEvidence(text='500',bbox=[190,88,310,122],source='tesseract',confidence=.9)]
    assert wall_candidates([seg(100,100,500,100),seg(100,110,500,110)],labels,900,600)==[]

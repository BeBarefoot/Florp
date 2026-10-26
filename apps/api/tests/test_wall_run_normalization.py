from app.wall_segmentation import WallMaskReport, MaskLine
from app.wall_run_normalization import consolidate_wall_runs

def report(*lines):
    return WallMaskReport(coverage_fraction=.03,line_count=len(lines),lines=list(lines))
def h(y,a,b):
    return MaskLine(x1=a,y1=y,x2=b,y2=y,support=.92)
def v(x,a,b):
    return MaskLine(x1=x,y1=a,x2=x,y2=b,support=.9)

def test_duplicate_parallel_mask_runs_become_one_wall():
    result=consolidate_wall_runs(report(h(100,15,270),h(103,26,240)))
    assert result.line_count==1
    assert result.lines[0].y1==100
    assert result.lines[0].x1==15
    assert result.lines[0].x2==270

def test_small_segment_extension_joins_and_retains_axis():
    result=consolidate_wall_runs(report(h(100,15,160),h(102,159,250)))
    assert result.line_count==1
    assert result.lines[0].x2==250

def test_window_sized_gap_remains_open():
    result=consolidate_wall_runs(report(h(100,15,160),h(100,220,360)))
    assert result.line_count==2

def test_perpendicular_junction_is_not_erased():
    result=consolidate_wall_runs(report(h(100,15,300),v(155,100,290)))
    assert result.line_count==2
    assert any(line.x1==line.x2 for line in result.lines)
    assert any(line.y1==line.y2 for line in result.lines)

def test_distant_parallel_walls_not_merged():
    result=consolidate_wall_runs(report(h(100,15,300),h(120,15,300)))
    assert result.line_count==2

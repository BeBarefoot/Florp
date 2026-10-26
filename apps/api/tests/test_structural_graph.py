from app.geometry import Geometry,Wall,Pt
from app.structural_graph import build_structural_graph

def wall(id,a,b):
    return Wall(id=id,start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1]))

def graph(*walls):
    return build_structural_graph(Geometry(width_px=500,height_px=500,walls=list(walls)))

def test_square_has_one_component_and_no_dangling_nodes():
    g=graph(wall('top',(100,100),(300,100)),
            wall('right',(300,100),(300,300)),
            wall('bottom',(300,300),(100,300)),
            wall('left',(100,300),(100,100)))
    assert g.disconnected_components==1
    assert g.dangling_nodes==0
    assert len(g.nodes)==4
    assert len(g.edges)==4

def test_partition_t_junctions_split_existing_wall_edges():
    g=graph(wall('top',(100,100),(300,100)),
            wall('bottom',(100,300),(300,300)),
            wall('partition',(200,100),(200,300)))
    assert len(g.edges)==5
    assert len([n for n in g.nodes if n.degree==3])==2

def test_crossing_creates_one_shared_junction():
    g=graph(wall('horizontal',(20,100),(300,100)),
            wall('vertical',(160,20),(160,190)))
    assert len(g.edges)==4
    assert len([n for n in g.nodes if n.degree==4])==1
    assert g.disconnected_components==1

def test_parallel_nearby_walls_remain_disconnected():
    g=graph(wall('a',(20,100),(300,100)),
            wall('b',(20,104),(300,104)))
    assert g.disconnected_components==2
    assert g.dangling_nodes==4

def test_opening_sized_gap_is_not_invented():
    g=graph(wall('a',(20,100),(120,100)),
            wall('b',(180,100),(300,100)))
    assert g.disconnected_components==2

def test_graph_generation_does_not_change_original_walls():
    source=Geometry(width_px=500,height_px=500,walls=[
        wall('a',(20,100),(300,100)),wall('b',(160,20),(160,190))])
    before=source.model_dump()
    build_structural_graph(source)
    assert source.model_dump()==before

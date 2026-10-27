from app.geometry import Geometry,Wall,Pt,Opening
from app.connectivity_preview import preview_connectivity
import pytest

def wall(id,a,b):
    return Wall(id=id,start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1]))

def test_t_junction_moves_only_loose_endpoint_without_changing_saved_input():
    g=Geometry(width_px=300,height_px=200,walls=[
        wall('horizontal',(20,100),(220,100)),
        wall('vertical',(120,50),(120,96)),
    ])
    original=g.model_dump()
    result=preview_connectivity(g)
    assert result.geometry.walls[1].end==Pt(x=120,y=100)
    assert result.geometry.walls[0]==g.walls[0]
    assert result.geometry.structure_reviewed is False
    assert len(result.changes)==1
    assert result.changes[0].reason=='perpendicular T junction'
    assert g.model_dump()==original
    assert result.after_dangling<=result.before_dangling

def test_endpoint_join_keeps_line_axis():
    g=Geometry(width_px=300,height_px=200,walls=[
        wall('a',(10,80),(100,80)),
        wall('b',(104,80),(210,80))])
    result=preview_connectivity(g)
    assert all(w.start.y==80 and w.end.y==80 for w in result.geometry.walls)
    assert any(c.distance_px<=5 for c in result.changes)
    assert g.walls[1].start.x==104

def test_does_not_bridge_large_missing_partition_or_parallel_wall_thickness():
    g=Geometry(width_px=300,height_px=200,walls=[
        wall('a',(10,50),(95,50)),
        wall('b',(120,50),(210,50)),
        wall('parallel',(10,56),(95,56))])
    result=preview_connectivity(g)
    assert result.changes==[]

def test_doors_windows_are_never_shifted_or_dropped():
    g=Geometry(width_px=300,height_px=200,px_per_meter=50,
        walls=[wall('host',(20,100),(220,100)),
               wall('t',(120,50),(120,97))],
        openings=[Opening(id='door',kind='door',wall_id='t',offset_m=0,
                          width_m=.4,height_m=2.1)])
    result=preview_connectivity(g)
    assert result.geometry.walls[1]==g.walls[1]
    assert result.geometry.openings==g.openings

def test_pure_read_only_preview_has_no_metric_or_room_changes():
    from app.geometry import Room
    g=Geometry(width_px=300,height_px=200,rooms=[
        Room(id='verified',points=[Pt(x=20,y=20),Pt(x=250,y=20),Pt(x=250,y=170)]),
    ],walls=[wall('a',(10,80),(100,80)),wall('b',(104,80),(210,80))])
    r=preview_connectivity(g)
    assert r.geometry.rooms==g.rooms
    assert r.geometry.px_per_meter is None
    assert all(w.id in ('a','b') for w in r.geometry.walls)

def test_tolerance_is_bounded():
    with pytest.raises(ValueError):
        preview_connectivity(Geometry(width_px=100,height_px=100),20)

def test_exact_starter_rectangle_removed_from_preview_not_saved():
    from app.geometry import fallback_geometry
    g=fallback_geometry(992,440)
    g.walls.append(wall('reviewed-wall',(200,80),(200,220)))
    result=preview_connectivity(g)
    assert result.removed_starter_ids==['w0','w1','w2','w3']
    assert [w.id for w in result.geometry.walls]==['reviewed-wall']
    assert result.geometry.rooms==[]
    assert len(g.walls)==5
    assert g.rooms[0].id=='room-1'
    assert result.geometry.structure_reviewed is False

def test_keep_manually_edited_starter_id():
    from app.geometry import fallback_geometry
    g=fallback_geometry(992,440)
    g.walls[0].start.x+=10
    result=preview_connectivity(g)
    assert 'w0' not in result.removed_starter_ids
    assert any(w.id=='w0' for w in result.geometry.walls)

def test_do_not_delete_opening_hosted_by_starter_wall():
    from app.geometry import fallback_geometry
    g=fallback_geometry(992,440)
    g.openings.append(Opening(id='door-1',kind='door',wall_id='w0',
        offset_m=.1,width_m=.6,height_m=2.1))
    result=preview_connectivity(g)
    assert 'w0' not in result.removed_starter_ids
    assert any(w.id=='w0' for w in result.geometry.walls)
    assert result.geometry.openings==g.openings

def test_opening_association_is_read_only_and_keeps_unmatched_labels(tmp_path,monkeypatch):
    import hashlib
    import cv2
    import numpy as np
    from sqlmodel import SQLModel,Session,create_engine
    from sqlalchemy.pool import StaticPool
    from app import main
    from app.models import Project,Blueprint,Layout,FusionCandidateReview
    from app.geometry import fallback_geometry
    db=create_engine('sqlite://',connect_args={'check_same_thread':False},
                     poolclass=StaticPool)
    SQLModel.metadata.create_all(db)
    monkeypatch.setattr(main,'engine',db)
    image=tmp_path/'source.png'
    assert cv2.imwrite(str(image),np.full((200,300,3),255,dtype='uint8'))
    digest=hashlib.sha256(image.read_bytes()).hexdigest()
    g=fallback_geometry(300,200)
    g.walls.append(wall('reviewed',(20,100),(260,100)))
    with Session(db) as session:
        project=Project(title='Opening review');session.add(project);session.flush()
        blueprint=Blueprint(project_id=project.id,filename='source.png',
                            preview_path=str(image),local_path=str(image),width=300,height=200)
        session.add(blueprint);session.flush()
        session.add(Layout(blueprint_id=blueprint.id,version=1,geometry=g.model_dump()))
        for i,start,end in [(0,(100,100),(140,100)),(1,(100,20),(140,20))]:
            session.add(FusionCandidateReview(
                blueprint_id=blueprint.id,preview_sha256=digest,
                candidate_id=f'opening-{i}',decision='door',category='yytsi_only',
                candidate={'id':f'opening-{i}','start':{'x':start[0],'y':start[1]},
                           'end':{'x':end[0],'y':end[1]}}))
        session.commit()
        bid=blueprint.id
    result=main.preview_reviewed_openings(bid,main.OpeningAssociationPreviewBody(geometry=g))
    assert result['saved'] is False
    assert result['proposed']==1
    assert result['unresolved']==1
    assert result['items'][0]['host_wall_id']=='reviewed'
    assert all(item['status'] in ('proposed','unresolved') for item in result['items'])
    with Session(db) as session:
        assert session.get(Layout,session.exec(
            __import__('sqlmodel').select(Layout.id)).first()).geometry==g.model_dump()


def test_offset_l_corner_joins_at_axis_intersection_without_kinking_lines():
    g=Geometry(width_px=300,height_px=200,walls=[
        wall('horizontal',(20,80),(101,80)),
        wall('vertical',(105,84),(105,160))])
    original=g.model_dump()
    r=preview_connectivity(g,tolerance_px=6)
    assert r.geometry.walls[0].end==Pt(x=105,y=80)
    assert r.geometry.walls[1].start==Pt(x=105,y=80)
    assert len([c for c in r.changes if c.reason=='perpendicular corner'])==2
    assert g.model_dump()==original

def test_corner_join_respects_tolerance_and_opening_hosts():
    g=Geometry(width_px=300,height_px=200,walls=[
        wall('a',(20,80),(100,80)),wall('b',(107,88),(107,160))])
    assert not any(c.reason=='perpendicular corner' for c in preview_connectivity(g,tolerance_px=5).changes)
    g.walls[1].start=Pt(x=104,y=84)
    g.openings=[Opening(id='window',kind='window',wall_id='b',
                         offset_m=0,width_m=.3,height_m=1)]
    r=preview_connectivity(g,tolerance_px=6)
    assert r.geometry.walls[1]==g.walls[1]
    assert not any(c.reason=='perpendicular corner' for c in r.changes)

def test_parallel_nearby_endpoints_never_corner_join():
    g=Geometry(width_px=300,height_px=200,walls=[
        wall('a',(20,80),(100,80)),wall('b',(104,84),(180,84))])
    r=preview_connectivity(g,tolerance_px=6)
    assert not any(c.reason=='perpendicular corner' for c in r.changes)

from scripts.analyze_training import summarize
def test_negative_only_dataset_not_marked_trained():
    x=summarize({'annotations':[{'label':'not_wall','x1':0,'y1':0,'x2':1,'y2':1}],
                 'manually_drawn_walls':[]})
    assert x['labels']['not_wall']==1
    assert x['ready_to_train'] is False
def test_duplicates_counted():
    a={'label':'wall','x1':1,'y1':2,'x2':3,'y2':4}
    assert summarize({'annotations':[a,a]})['duplicated_segments']==1

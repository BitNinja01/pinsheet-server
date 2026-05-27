def test_make_round_creates_valid_shape(make_round):
    r = make_round(gross=80, fir_hits=10, gir_hits=8)
    assert r["date"] == "2026-05-15"
    assert r["total_gross"] == "80"
    assert r["differential"] == "12.0"
    assert len(r["holes"]) == 18
    assert r["holes"]["1"]["gross"] is not None
    assert "fairway" in r["holes"]["1"]

def test_make_course_creates_valid_shape(make_course):
    c = make_course(name="Pebble Beach", par=72)
    assert "Pebble Beach" in c
    assert c["Pebble Beach"]["par"] == "72"
    assert "White" in c["Pebble Beach"]["tees"]
    assert c["Pebble Beach"]["tees"]["White"]["slope"] == 128

def test_sample_rounds_has_3_rounds(sample_rounds):
    assert len(sample_rounds) == 3

def test_empty_courses_is_empty_dict(empty_courses):
    assert empty_courses == {}

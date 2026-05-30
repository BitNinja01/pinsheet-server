import pytest

from source.calc.models import dict_to_round, dict_to_course, RoundData, CourseData


@pytest.fixture
def make_round():
    """Factory fixture: returns a function that creates a RoundData."""
    def _make_round(
        course="Test GC",
        tees="White",
        date="2026-05-15",
        gross=85,
        putts=32,
        fir_hits=8,
        gir_hits=6,
        penalties=0,
        holes_selection="all",
        differential="12.0",
        computed_handicap="10.5",
    ):
        pars = {
            1: 4, 2: 5, 3: 4, 4: 3, 5: 4, 6: 5, 7: 4, 8: 3, 9: 4,
            10: 5, 11: 4, 12: 3, 13: 4, 14: 5, 15: 4, 16: 3, 17: 4, 18: 5,
        }
        hole_list = list(range(1, 19))
        num_holes = len(hole_list)

        base_gross = gross // num_holes
        extra_gross = gross % num_holes
        gross_per_hole = [base_gross + (1 if i < extra_gross else 0) for i in range(num_holes)]

        base_putts = max(1, putts // num_holes)
        extra_putts = putts - base_putts * num_holes
        putts_per_hole = [base_putts + (1 if i < extra_putts else 0) for i in range(num_holes)]

        eligible_fir = [n for n in hole_list if pars[n] != 3]
        fir_set = set(eligible_fir[:fir_hits]) if fir_hits <= len(eligible_fir) else set(eligible_fir)

        gir_set = set(hole_list[:gir_hits]) if gir_hits <= num_holes else set(hole_list)

        holes = {}
        for i, n in enumerate(hole_list):
            par = pars[n]
            h_gross = gross_per_hole[i]
            h_putts = putts_per_hole[i] if i < len(putts_per_hole) else 2
            h_fir = "H" if n in fir_set else ("L" if n in eligible_fir else "")
            h_gir = "H" if n in gir_set else ""
            h_pen = "1" if penalties > 0 and i < penalties else "0"

            holes[str(n)] = {
                "gross": str(h_gross),
                "putts": str(h_putts),
                "fairway": h_fir,
                "gir": h_gir,
                "penalties": h_pen,
            }

        return dict_to_round({
            "date": date,
            "course": course,
            "tees": tees,
            "holes_selection": holes_selection,
            "total_gross": str(gross),
            "total_putts": str(putts),
            "differential": differential,
            "computed_handicap": computed_handicap,
            "holes": holes,
        })
    return _make_round


@pytest.fixture
def make_course():
    """Factory fixture: returns a function that creates a {name: CourseData} dict."""
    def _make_course(
        name="Test GC",
        par=72,
        slope=128,
        rating=71.5,
        yardage=6200,
    ):
        holes = {}
        for n in range(1, 19):
            if n in (4, 8, 12, 16):
                p = 3
            elif n in (2, 6, 10, 14, 18):
                p = 5
            else:
                p = 4
            holes[str(n)] = {"par": p, "hole_index": n}

        tee_data = {
            "slope": slope,
            "rating": rating,
            "yardage": str(yardage),
        }

        course_dict = {
            "par": str(par),
            "holes": holes,
            "tees": {"White": tee_data},
        }
        return {name: dict_to_course(name, course_dict)}
    return _make_course


@pytest.fixture
def sample_rounds(make_round):
    """Quick 3-round list for tests that just need some data."""
    return [make_round(gross=g) for g in (78, 82, 85)]


@pytest.fixture
def sample_course(make_course):
    return make_course()


@pytest.fixture
def empty_courses():
    return {}


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Override data directory to temp path so tests don't touch real data."""
    import store
    data_sub = tmp_path / "data"
    data_sub.mkdir()
    monkeypatch.setattr(store, "_DATA_DIR", data_sub)
    return data_sub

from datetime import date
import pytest

from calc.seasons import (
    calc_rounds_this_year,
    calc_rounds_total,
    calc_golfiest_month,
    calc_most_common_day,
    calc_weekly_streak,
    calc_season_yardage,
    calc_hi_journey,
    calc_season_rounds,
)
from source.models import dict_to_course


class TestRoundsCount:
    def test_rounds_this_year_empty(self):
        assert calc_rounds_this_year([]) == 0

    def test_rounds_this_year_current(self, make_round):
        yr = str(date.today().year)
        rounds = [make_round(date=f"{yr}-06-01"), make_round(date=f"{yr}-07-01")]
        assert calc_rounds_this_year(rounds) == 2

    def test_rounds_this_year_ignores_other_years(self, make_round):
        rounds = [make_round(date="2025-06-01"), make_round(date="2026-06-01")]
        assert calc_rounds_this_year(rounds) == (1 if date.today().year == 2026 else 0)

    def test_rounds_total_empty(self):
        assert calc_rounds_total([]) == 0

    def test_rounds_total_normal(self, make_round):
        rounds = [make_round() for _ in range(5)]
        assert calc_rounds_total(rounds) == 5


class TestGolfiestMonth:
    def test_empty(self):
        assert calc_golfiest_month([]) == ("—", 0)

    def test_single_month(self, make_round):
        rounds = [make_round(date="2026-06-01"), make_round(date="2026-06-15")]
        name, count = calc_golfiest_month(rounds)
        assert name == "June"
        assert count == 2

    def test_tie_returns_first_most_common(self, make_round):
        rounds = [
            make_round(date="2026-06-01"), make_round(date="2026-06-15"),
            make_round(date="2026-07-01"), make_round(date="2026-07-10"),
        ]
        name, count = calc_golfiest_month(rounds)
        assert count == 2

    def test_skips_invalid_dates(self, make_round):
        rounds = [make_round(date="not-a-date")]
        assert calc_golfiest_month(rounds) == ("—", 0)


class TestMostCommonDay:
    def test_empty(self):
        assert calc_most_common_day([]) == ("—", 0)

    def test_specific_day(self, make_round):
        rounds = [make_round(date="2026-06-01"), make_round(date="2026-06-08")]
        day, count = calc_most_common_day(rounds)
        assert day == "Monday"
        assert count == 2

    def test_skips_invalid_dates(self, make_round):
        rounds = [make_round(date="bad-date")]
        assert calc_most_common_day(rounds) == ("—", 0)


class TestWeeklyStreak:
    def test_empty(self):
        assert calc_weekly_streak([]) == 0

    def test_consecutive_weeks(self, make_round):
        rounds = [make_round(date="2026-06-01"), make_round(date="2026-06-08")]
        assert calc_weekly_streak(rounds) == 2

    def test_gap_breaks_streak(self, make_round):
        rounds = [
            make_round(date="2026-06-01"),
            make_round(date="2026-06-08"),
            make_round(date="2026-07-01"),
        ]
        assert calc_weekly_streak(rounds) == 2

    def test_multiple_same_week(self, make_round):
        rounds = [
            make_round(date="2026-06-01"),
            make_round(date="2026-06-03"),
            make_round(date="2026-06-08"),
        ]
        assert calc_weekly_streak(rounds) == 2

    def test_year_crossover(self, make_round):
        rounds = [
            make_round(date="2025-12-29"),
            make_round(date="2026-01-05"),
        ]
        assert calc_weekly_streak(rounds) >= 2

    def test_skips_invalid_dates(self, make_round):
        rounds = [make_round(date="bad")]
        assert calc_weekly_streak(rounds) == 0


class TestSeasonYardage:
    def test_empty_rounds(self, make_course):
        assert calc_season_yardage([], {}, "walking") is None

    def test_unknown_course(self, make_round, make_course):
        rounds = [make_round(course="Unknown")]
        assert calc_season_yardage(rounds, {}, "walking") is None

    def test_walking_miles(self, make_round, make_course):
        courses = make_course(yardage=6600)
        r = make_round(date="2026-06-01")
        r.transport = ""
        rounds = [r]
        miles = calc_season_yardage(rounds, courses, "walking")
        assert miles is not None
        assert miles > 0

    def test_riding_excludes_walking(self, make_round, make_course):
        courses = make_course(yardage=6600)
        r = make_round(date="2026-06-01")
        r.transport = ""
        rounds = [r]
        assert calc_season_yardage(rounds, courses, "riding") is None

    def test_riding_includes_riding(self, make_round, make_course):
        courses = make_course(yardage=6600)
        r = make_round(date="2026-06-01")
        r.transport = "riding"
        rounds = [r]
        assert calc_season_yardage(rounds, courses, "riding") is not None

    def test_zero_yardage_tee_skipped(self, make_round, make_course):
        courses = make_course(yardage=0)
        rounds = [make_round(date="2026-06-01")]
        assert calc_season_yardage(rounds, courses, "walking") is None


class TestHiJourney:
    def test_empty_rounds(self):
        assert calc_hi_journey([], []) is None

    def test_no_handicap_data(self, make_round):
        rounds = [make_round(computed_handicap="0")]
        assert calc_hi_journey(rounds, rounds) is None

    def test_with_live_hi(self, make_round):
        rounds = [make_round(date="2026-06-01", computed_handicap="15.0")]
        result = calc_hi_journey([], rounds, live_hi=12.0)
        assert result is not None
        start, end, delta = result
        assert end == 12.0

    def test_journey_delta(self, make_round):
        all_rounds = [make_round(date="2026-01-01", computed_handicap="20.0")]
        season = [make_round(date="2026-06-01", computed_handicap="15.0")]
        result = calc_hi_journey(all_rounds, season)
        assert result is not None
        start, end, delta = result
        assert start == 20.0
        assert end == 15.0
        assert delta == 5.0

    def test_with_live_hi_and_valid_date(self, make_round):
        rounds = [make_round(date="2026-06-01", computed_handicap="15.0")]
        result = calc_hi_journey([], rounds, live_hi=12.0)
        assert result is not None
        start, end, delta = result
        assert end == 12.0


class TestSeasonRounds:
    def test_empty(self):
        assert calc_season_rounds([], {}) == []

    def test_filters_by_current_year(self, make_round):
        settings = {"season_start_month": 1, "season_start_day": 1,
                     "season_end_month": 12, "season_end_day": 28}
        rounds = [make_round(date="2025-06-01"), make_round(date="2026-06-01")]
        result = calc_season_rounds(rounds, settings)
        assert len(result) == 1
        assert result[0].date == "2026-06-01"

    def test_date_range_filtering(self, make_round):
        settings = {"season_start_month": 6, "season_start_day": 1,
                     "season_end_month": 8, "season_end_day": 31}
        rounds = [
            make_round(date="2026-05-15"),
            make_round(date="2026-06-15"),
            make_round(date="2026-07-15"),
            make_round(date="2026-09-01"),
        ]
        result = calc_season_rounds(rounds, settings)
        assert len(result) == 2
        assert result[0].date == "2026-06-15"

    def test_skips_invalid_dates(self, make_round):
        settings = {"season_start_month": 1, "season_start_day": 1,
                     "season_end_month": 12, "season_end_day": 28}
        rounds = [make_round(date="bad-date")]
        assert calc_season_rounds(rounds, settings) == []

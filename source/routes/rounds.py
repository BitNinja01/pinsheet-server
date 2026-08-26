import logging
import re
from datetime import date

from flask import render_template, request, jsonify, g, current_app
from flask_login import login_required, current_user

from store import (
    load_round_draft, save_round_draft, clear_round_draft,
    load_course_draft, save_course_draft, clear_course_draft,
    get_slope_rating, save_round, update_round, delete_round,
    get_matches_for_user, link_round, get_match,
    recompute_all_handicaps,
    recompute_handicaps_for_user,
    set_round_excluded,
    next_round_index,
)
from calc import (
    calc_round_dif, round_half_up, calc_handicap_index, calc_round_vs_par,
    calc_avg_vs_par, calc_round_vs_rating, calc_avg_vs_rating,
    calc_par_or_better_percent, calc_big_number_rate, calc_fir_percent,
    calc_gir_percent, calc_putts_per_round, calc_one_putt_percent,
    calc_two_putt_percent, calc_three_putt_percent, calc_scramble_percent,
    calc_scoring_avg_by_par_type, calc_penalties_per_round,
    calc_scoring_average,
    get_best_n_rounds, last_n_rounds,
    calc_course_handicap,
    calc_adjusted_gross_score,
    calc_playing_handicap,
    calc_hole_scores,
    calc_9hole_dif,
    WHS_HANDICAP_WINDOW,
    WHS_MAX_HANDICAP_INDEX,
    current_and_previous_handicap_index,
)
from source.web.charts import sparkline_svg
from calc import per_round_hole_stats
from source.models import dict_to_round, dict_to_course, clamp_pcc, effective_pcc
from source.plugin import fire_hook, _plugins
from source.request_data import get_settings, get_courses, get_all_rounds_for_user, base_context

_log = logging.getLogger("pinsheet")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_date(val) -> bool:
    """True for a well-formed ISO YYYY-MM-DD string. Keeps a malformed date out
    of the DB (and out of the client-side redirect that builds a round URL)."""
    return isinstance(val, str) and bool(_DATE_RE.match(val))


def _safe_int(val, default=0):
    """Parse an int from user input, tolerating blank/non-numeric values."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _prior_displayed_hi_or_none(rounds, before_date: str, before_index) -> float | None:
    """The Handicap Index IN EFFECT for a round dated `before_date`/`before_index`
    = the most recent CHRONOLOGICALLY-PRIOR round's DISPLAYED (Rule 5.8-capped /
    5.9-ESR-adjusted) Handicap Index, i.e. its stored computed_handicap. Returns
    None when none is established yet.

    Mirrors recompute_handicaps_for_user's `prior_displayed[-1]` so the ESC
    (Rule 3 / Rule 12) adjusted gross and the 9-hole differential combine are
    computed on the same basis regardless of entry path. `rounds` is
    most-recent-first (date DESC, index DESC), so the first entry that is
    strictly before (before_date, before_index) AND carries a real
    computed_handicap is the correct in-effect HI. Filtering by date is
    essential: a BACKDATED round must not take a chronologically-later round's HI
    as its "prior" (that would diverge from a full recompute).
    """
    bidx = _safe_int(before_index, -1)
    for r in rounds:
        r_idx = _safe_int(getattr(r, "index", -1), -1)
        is_prior = r.date < before_date or (r.date == before_date and r_idx < bidx)
        if not is_prior:
            continue
        ch = getattr(r, "computed_handicap", None)
        if ch and ch not in ("0", ""):
            try:
                return float(ch)
            except (ValueError, TypeError):
                continue
    return None


def _prior_displayed_hi(rounds, before_date: str, before_index) -> float:
    """0.0-collapsed variant of `_prior_displayed_hi_or_none`: the ESC
    (Rule 3 / Rule 12) path derives the course handicap from HI 0.0 when no
    prior displayed Handicap Index exists yet, so this returns 0.0 (not None)
    in that case. Preserves the exact float contract for `adj_hi = hi_before / 2`."""
    hi = _prior_displayed_hi_or_none(rounds, before_date, before_index)
    return 0.0 if hi is None else hi


def _scored_hole_count(holes):
    """Number of holes with a real (positive) gross entered."""
    return sum(1 for h in holes.values() if _safe_int(h.get("gross"), 0) > 0)


def _expected_hole_count(course, holes_sel):
    """How many holes a complete round of this selection should have."""
    if holes_sel == "all":
        return len(course.get("holes", {})) or 18
    return 9


MAX_HOLE_GROSS = 20  # sane per-hole ceiling (issue #80, CWE-20)


def _sanitize_scores(data, course, holes_sel):
    """Clamp score fields in place so a crafted or buggy client can't poison the
    submitter's handicap with negative or absurd scores (issue #80, CWE-20).

    Consistent with the app's lenient contract (malformed input must not 500):
    non-numeric/blank gross stays unscored via _safe_int's 0 fallback rather
    than erroring. Per-hole gross is clamped to [0, MAX_HOLE_GROSS]; a
    score-only total is clamped to [0, MAX_HOLE_GROSS * holes_played].
    """
    for hole in (data.get("holes") or {}).values():
        raw = hole.get("gross", "")
        if raw in (None, ""):
            continue
        hole["gross"] = str(max(0, min(_safe_int(raw, 0), MAX_HOLE_GROSS)))
    if data.get("entry_mode") == "score_only":
        raw_total = data.get("gross_total", "")
        if raw_total not in (None, ""):
            max_total = MAX_HOLE_GROSS * _expected_hole_count(course, holes_sel)
            data["gross_total"] = str(max(0, min(_safe_int(raw_total, 0), max_total)))


def register_rounds_routes(app, csrf):
    @app.route("/rounds/new")
    @login_required
    def round_entry():
        today = date.today().isoformat()
        no_courses = len(get_courses()) == 0
        matches = get_matches_for_user(current_user.id)
        return render_template("round_entry.html", **base_context(
            current_page="round_entry",
            courses=get_courses(), today=today, no_courses=no_courses,
            matches=matches,
        ))

    @app.route("/rounds")
    @login_required
    def rounds_list():
        settings = get_settings()
        all_rounds_for_user = get_all_rounds_for_user()
        include_9hole = settings.get("include_9hole", True)

        rounds_data = []
        for r in all_rounds_for_user:
            course = get_courses().get(r.course, {})
            total = r.total_gross
            course_holes = course.get("holes", {})
            if r.holes_selection != "all" and course_holes:
                if r.holes:
                    played_par = sum(int(course_holes.get(hn, {}).get("par", 0)) for hn in r.holes)
                else:
                    hole_nums = sorted(course_holes.keys(), key=int)
                    half = hole_nums[:9] if r.holes_selection == "front" else hole_nums[9:18]
                    played_par = sum(int(course_holes[hn].get("par", 0)) for hn in half)
            else:
                played_par = int(course.get("par", 0))
            score_to_par = int(total) - played_par if total and played_par and total != "0" else None
            raw_mode = r.entry_mode
            display_mode = "normal" if raw_mode == "detailed" else (raw_mode or "score_only")

            net_score = None
            net_to_par = None
            if r.computed_handicap:
                try:
                    hi = float(r.computed_handicap)
                    tee_data = course.get("tees", {}).get(r.tees, {}) if r.tees else {}
                    slope, rating = get_slope_rating(tee_data, r.holes_selection)
                    if hi and slope:
                        adj_hi = hi / 2 if r.holes_selection != "all" else hi
                        ch = calc_course_handicap(adj_hi, played_par, slope, rating)
                        net_score = int(total) - ch
                        net_to_par = net_score - played_par
                except (ValueError, TypeError):
                    pass

            sparkline = sparkline_svg(r.holes)

            hs = per_round_hole_stats(r.holes, course.get("holes", {}))
            fir_display = hs["fir_display"]
            gir_display = hs["gir_display"]
            scr_display = hs["scr_display"]
            total_putts = hs["total_putts"]

            rounds_data.append({
                "date": r.date,
                "course": r.course,
                "tees": r.tees,
                "total": total,
                "score_to_par": score_to_par,
                "net": net_score,
                "net_to_par": net_to_par,
                "differential": r.differential,
                "index": r.index,
                "in_handicap": False,
                "excluded": r.excluded,
                "entry_mode_display": display_mode,
                "sparkline": sparkline,
                "fir_display": fir_display,
                "gir_display": gir_display,
                "scr_display": scr_display,
                "putts": total_putts,
            })

        # WHS Rule 5.2: the current handicap index uses the best-N
        # differentials from the most recent 20 ELIGIBLE rounds, so only
        # that window can light up. all_rounds_for_user is most-recent-first
        # already; pass it in full with an explicit window rather than
        # pre-truncating to raw [:20], which would under-count (and diverge
        # from the stored/recompute Handicap Index) when excluded/"0"/
        # 9-hole-gated rounds sit within the raw most-recent-20.
        best_rounds = get_best_n_rounds(all_rounds_for_user, include_9hole, window=WHS_HANDICAP_WINDOW)
        best_keys = {(r.date, r.index) for r in best_rounds}
        for rd in rounds_data:
            if (rd["date"], rd["index"]) in best_keys:
                rd["in_handicap"] = True

        return render_template("rounds_list.html", **base_context(
            current_page="rounds_list",
            rounds=rounds_data,
            settings=settings,
            include_9hole=include_9hole,
        ))

    @app.route("/api/drafts/round", methods=["GET"])
    @login_required
    def api_draft_round_get():
        draft = load_round_draft(current_user.id)
        return jsonify(draft or {})

    @app.route("/api/drafts/round", methods=["PUT"])
    @login_required
    @csrf.exempt
    def api_draft_round_put():
        save_round_draft(request.get_json(), current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/drafts/round", methods=["DELETE"])
    @login_required
    @csrf.exempt
    def api_draft_round_delete():
        clear_round_draft(current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/drafts/course", methods=["GET"])
    @login_required
    def api_draft_course_get():
        draft = load_course_draft(current_user.id)
        return jsonify(draft or {})

    @app.route("/api/drafts/course", methods=["PUT"])
    @login_required
    @csrf.exempt
    def api_draft_course_put():
        save_course_draft(request.get_json(), current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/drafts/course", methods=["DELETE"])
    @login_required
    @csrf.exempt
    def api_draft_course_delete():
        clear_course_draft(current_user.id)
        return jsonify({"ok": True})

    @app.route("/api/rounds", methods=["POST"])
    @login_required
    @csrf.exempt
    def api_rounds_post():
        data = request.get_json()
        date_val = data.get("date", "")
        if not _valid_date(date_val):
            return jsonify({"error": "Invalid date"}), 400
        course_name = data.get("course", "")
        tees_name = data.get("tees", "")
        match_id = data.get("match_id")

        course = get_courses().get(course_name, {})
        tees = course.get("tees", {}).get(tees_name, {})

        holes_sel = data.get("holes_played", "18")
        if holes_sel == "front9":
            holes_sel = "front"
        elif holes_sel == "back9":
            holes_sel = "back"
        else:
            holes_sel = "all"

        slope, rating = get_slope_rating(tees, holes_sel)

        _sanitize_scores(data, course, holes_sel)

        # WHS Rule 5.6 / 5.1a: PCC (Playing Conditions Calculation) is an
        # OPTIONAL per-round input (a single-user app can't compute the
        # handicap authority's field-wide PCC itself) -- default 0.0 (no
        # adjustment, current/prior behavior) if omitted, clamped to
        # [-1.0, +3.0] (WHS Rule 5.6's own bound) if provided, non-numeric
        # input defaults to 0.0. See clamp_pcc for the full contract.
        pcc = clamp_pcc(data.get("pcc", 0))

        golf_round = {
            "date": date_val,
            "course": course_name,
            "tees": tees_name,
            "holes_played": data.get("holes_played", "18"),
            "holes_selection": holes_sel,
            "transport": data.get("transport", ""),
            "entry_mode": data.get("entry_mode", "detailed"),
            "notes": data.get("notes", ""),
            "holes": data.get("holes", {}),
            "gross_total": data.get("gross_total", ""),
            "pcc": pcc,
        }

        total_gross = 0
        if data.get("entry_mode") == "score_only":
            total_gross = _safe_int(data.get("gross_total"), 0)
            golf_round["total_gross"] = str(total_gross)
        elif data.get("holes"):
            for h in data["holes"].values():
                total_gross += _safe_int(h.get("gross"), 0)
            golf_round["total_gross"] = str(total_gross)

        # A round without a fair, complete score must not produce a differential
        # that poisons the handicap. Two cases: (a) an incomplete detailed round
        # (fewer holes scored than the selection requires), and (b) a round with
        # no real score at all (blank/zero gross). Both get the "0" sentinel.
        incomplete = (
            data.get("entry_mode") != "score_only"
            and bool(data.get("holes"))
            and _scored_hole_count(data["holes"]) < _expected_hole_count(course, holes_sel)
        )
        no_score = total_gross <= 0
        skip_differential = incomplete or no_score

        all_rounds_for_user = get_all_rounds_for_user()
        # The index this round WILL occupy (next_round_index gap-fills the lowest
        # free slot, so it is NOT necessarily the highest for its date) -- needed
        # up-front so the ESC prior-HI basis uses the round's true chronological
        # position among same-date rounds.
        index = next_round_index(date_val, current_user.id)
        adjusted_gross = total_gross
        if data.get("entry_mode") != "score_only" and data.get("holes"):
            # WHS Rule 3 (Net Double Bogey) / Rule 12: the ESC-adjusted gross
            # (and hence the Score Differential) must be identical regardless of
            # entry path. Derive the ESC course handicap from the HI IN EFFECT
            # -- the prior DISPLAYED (Rule 5.8-capped / 5.9-ESR-adjusted)
            # Handicap Index, i.e. the most recent chronologically-prior round's
            # stored computed_handicap (0.0 if none established yet) -- exactly
            # as recompute_handicaps_for_user and the zip-import path do. A fresh
            # raw calc_handicap_index() here omits the cap/ESR and diverges, and
            # skipping ESC entirely when no HI exists diverges from the backfill
            # paths (which apply it with course_handicap derived from HI 0.0).
            hi_before = _prior_displayed_hi(all_rounds_for_user, date_val, index)
            adj_hi = hi_before / 2 if holes_sel != "all" else hi_before
            course_holes = course.get("holes", {})
            if holes_sel != "all" and course_holes:
                hole_nums = sorted(course_holes.keys(), key=int)
                half = hole_nums[:9] if holes_sel == "front" else hole_nums[9:18]
                played_par = sum(int(course_holes[hn].get("par", 0)) for hn in half)
            else:
                played_par = int(course.get("par", 0))
            course_handicap = calc_course_handicap(adj_hi, played_par, slope, rating)
            ags = calc_adjusted_gross_score(data["holes"], course_holes, course_handicap)
            if ags is not None:
                adjusted_gross = ags

        if skip_differential:
            differential = 0.0
            # Exactly "0" is the sentinel that excludes a round from the
            # handicap calc (str(0.0) == "0.0" would NOT be excluded).
            golf_round["differential"] = "0"
        elif holes_sel != "all":
            # WHS 9-hole combine: base 9-hole Score Differential plus the
            # expected 9-hole adjustment keyed on the prior DISPLAYED HI (the
            # or_none variant -- a None prior means no established HI yet, so
            # the raw base is used; the 0.0-collapsed `hi_before` above is
            # NOT the right basis for the combine). WHS Rule 5.1b: only 50%
            # of the day's PCC applies to a 9-hole score (effective_pcc).
            differential = calc_9hole_dif(
                slope, adjusted_gross, rating,
                _prior_displayed_hi_or_none(all_rounds_for_user, date_val, index),
                effective_pcc(pcc, holes_sel),
            )
            golf_round["differential"] = str(differential)
        else:
            # WHS Rule 5.1b: 9-hole scores apply only 50% of the day's PCC --
            # effective_pcc halves `pcc` when holes_sel != "all" ("front"/
            # "back"), passes it through unchanged for "all" (18-hole).
            differential = calc_round_dif(slope, adjusted_gross, rating, effective_pcc(pcc, holes_sel))
            golf_round["differential"] = str(differential)

        golf_round_typed = dict_to_round(golf_round)
        all_rounds_for_user.insert(0, golf_round_typed)
        # Inserted at index 0 -- list stays most-recent-first (WHS ordering
        # contract).
        new_hi = calc_handicap_index(all_rounds_for_user, get_settings().get("include_9hole", True))
        # WHS Rule 5.3: `new_hi` here is a transient DISPLAYED value (this
        # row's `computed_handicap` before the recompute cascade below runs
        # and applies the real Rule 5.8 cap using the player's LHI) -- clamp
        # it to the 54.0 maximum. `calc_handicap_index` intentionally
        # returns the raw, unclamped Rule 5.2/5.2a value (see its
        # docstring), so every displayed/stored site must clamp for itself.
        if new_hi is not None:
            new_hi = min(new_hi, WHS_MAX_HANDICAP_INDEX)
            golf_round["computed_handicap"] = str(new_hi)
            golf_round_typed.computed_handicap = str(new_hi)

        # index computed above (before the ESC block) so both share one value
        round_id = save_round(golf_round, date_val, index, current_user.id)
        fire_hook("on_round_saved", round_data=golf_round, user_id=current_user.id, db_path=app.config["DB_PATH"])

        # WHS Rule 5.7/5.8 -- the value written above (`new_hi`) is the raw,
        # uncapped Handicap Index; only `recompute_handicaps_for_user` knows
        # the player's Low Handicap Index and applies the soft/hard cap. Run
        # it now so the row just saved (and any rounds after it) hold the
        # same capped value recompute would independently produce --
        # live-save must equal recompute for the capped value.
        # Tradeoff (accepted): this reruns the full O(n) sequential
        # recompute over the user's entire round history on every single
        # POST, rather than only updating the newly-saved row -- required
        # because Rule 5.7's LHI (and thus the cap applied to THIS round)
        # depends on the whole prior record, and later rounds may also need
        # their own cap re-evaluated. Acceptable at per-user round volumes
        # (hundreds, not millions); revisit with incremental/cached LHI
        # tracking if per-user round counts grow large enough to matter.
        recompute_handicaps_for_user(current_user.id)
        fresh_rounds = get_all_rounds_for_user(force=True)
        for fr in fresh_rounds:
            if fr.date == date_val and fr.index == index:
                if fr.computed_handicap:
                    golf_round["computed_handicap"] = fr.computed_handicap
                    golf_round_typed.computed_handicap = fr.computed_handicap
                break

        if match_id and golf_round.get("computed_handicap"):
            try:
                match_id = int(match_id)
                hi = float(golf_round["computed_handicap"])
                adj_hi = hi / 2 if holes_sel != "all" else hi
                course_holes = course.get("holes", {})
                if holes_sel != "all" and course_holes:
                    if golf_round.get("holes"):
                        played_par = sum(int(course_holes.get(hn, {}).get("par", 0)) for hn in golf_round.get("holes", {}))
                    else:
                        hole_nums = sorted(course_holes.keys(), key=int)
                        half = hole_nums[:9] if holes_sel == "front" else hole_nums[9:18]
                        played_par = sum(int(course_holes[hn].get("par", 0)) for hn in half)
                else:
                    played_par = int(course.get("par", 0))
                ch = calc_course_handicap(adj_hi, played_par, slope, rating)
                # WHS Rule 6.2 / Appendix C: reduce to a Playing Handicap
                # using the match's allowance percent (default 100 -- same
                # as the pre-Rule-6.2 full-Course-Handicap net) before
                # subtracting from gross.
                match = get_match(match_id)
                allowance = match.get("allowance_percent", 100) if match else 100
                ph = calc_playing_handicap(ch, allowance)
                net = total_gross - ph
                link_round(match_id, current_user.id, round_id, float(net))
            except (ValueError, TypeError, Exception) as exc:
                _log.warning("match linking failed — %s", exc)

        redirect_url = None
        for plugin in _plugins:
            fn = getattr(plugin, "post_save_redirect", None)
            if fn is not None:
                try:
                    url = fn(golf_round, current_user.id)
                    if url:
                        redirect_url = url
                        break
                except Exception as exc:
                    _log.warning("plugin %s: post_save_redirect() failed — %s", getattr(plugin, "plugin_info", {}).get("name", "?"), exc)

        return jsonify({"date": date_val, "index": index, "differential": differential, "redirect": redirect_url})

    @app.route("/rounds/<date>/<index>")
    @login_required
    def round_detail(date, index):
        all_rounds_for_user = get_all_rounds_for_user()
        round_data = None
        for r in all_rounds_for_user:
            if r.date == date and str(r.index) == str(index):
                round_data = r
                break
        if not round_data:
            return "Round not found", 404

        edit_mode = request.args.get("edit") == "1"
        course = get_courses().get(round_data.course, {})
        course_holes = course.get("holes", {})
        entry_mode = round_data.entry_mode
        tee_data = course.get("tees", {}).get(round_data.tees, {}) if round_data.tees else {}
        slope, rating = get_slope_rating(tee_data, round_data.holes_selection)

        rounds_before = [r for r in all_rounds_for_user
                         if r.date < round_data.date or (r.date == round_data.date and r.index < round_data.index)]
        # Filter preserves all_rounds_for_user's most-recent-first order
        # (WHS ordering contract).
        hi_before = calc_handicap_index(rounds_before, get_settings().get("include_9hole", True))
        # WHS Rule 5.3: `hi_before` is rendered directly on the round-detail
        # page ("HI Before") and feeds Course Handicap below -- clamp the
        # raw calc_handicap_index() value to the 54.0 maximum (no lower
        # clamp).
        if hi_before is not None:
            hi_before = min(hi_before, WHS_MAX_HANDICAP_INDEX)

        hole_nums_all = sorted(course_holes.keys(), key=int)
        if not hole_nums_all:
            total_par_course = 0
        elif round_data.holes_selection == "front":
            total_par_course = sum(int(course_holes[hn].get("par", 0)) for hn in hole_nums_all[:9])
        elif round_data.holes_selection == "back":
            total_par_course = sum(int(course_holes[hn].get("par", 0)) for hn in hole_nums_all[9:18])
        else:
            total_par_course = sum(int(course_holes[hn].get("par", 0)) for hn in hole_nums_all)

        course_handicap = None
        if hi_before is not None and slope:
            adj_hi = hi_before / 2 if round_data.holes_selection != "all" else hi_before
            course_handicap = calc_course_handicap(adj_hi, total_par_course, slope, rating)

        holes = []
        front_gross = back_gross = front_par = back_par = 0
        front_putts = back_putts = 0
        front_net = back_net = 0
        front_fir_hits = front_fir_eligible = 0
        back_fir_hits = back_fir_eligible = 0
        front_gir_hits = back_gir_hits = 0
        front_holes_cnt = back_holes_cnt = 0

        fir_hits = fir_eligible = 0
        gir_hits = 0
        total_putts = 0
        scramble_hits = scramble_opps = 0
        dist = {"eagle": 0, "birdie": 0, "par": 0, "bogey": 0, "double": 0, "worse": 0}
        net_dist = {"eagle": 0, "birdie": 0, "par": 0, "bogey": 0, "double": 0, "worse": 0}

        hole_data = round_data.holes
        hole_nums = sorted(hole_data.keys(), key=lambda x: int(x))

        for hn in hole_nums:
            h = hole_data[hn]
            hole_num = int(hn)
            par = int(course_holes.get(hn, {}).get("par", 0))
            gross = h.gross
            putts = h.putts
            pen = h.penalties
            fw = h.fairway
            gir = h.gir
            is_par3 = par == 3

            hole_index = int(course_holes.get(hn, {}).get("hole_index", 999))
            strokes = 0
            if course_handicap is not None:
                if hole_index <= course_handicap:
                    strokes += 1
                if hole_index <= course_handicap - 18:
                    strokes += 1
            net = gross - strokes
            net_diff = net - par
            yds = tee_data.get("yardages", {}).get(hn, "")

            if hole_num <= 9:
                front_gross += gross; front_par += par; front_putts += putts
                front_net += net; front_holes_cnt += 1
            else:
                back_gross += gross; back_par += par; back_putts += putts
                back_net += net; back_holes_cnt += 1

            if not is_par3:
                fir_eligible += 1
                if hole_num <= 9:
                    front_fir_eligible += 1
                else:
                    back_fir_eligible += 1
                if not fw or fw == "H":
                    fir_hits += 1
                    if hole_num <= 9:
                        front_fir_hits += 1
                    else:
                        back_fir_hits += 1

            if not gir or gir == "H":
                gir_hits += 1
                if hole_num <= 9:
                    front_gir_hits += 1
                else:
                    back_gir_hits += 1

            total_putts += putts

            if gir and gir != "H":
                scramble_opps += 1
                if gross <= par:
                    scramble_hits += 1

            diff_val = gross - par
            if diff_val <= -2:
                dist["eagle"] += 1
            elif diff_val == -1:
                dist["birdie"] += 1
            elif diff_val == 0:
                dist["par"] += 1
            elif diff_val == 1:
                dist["bogey"] += 1
            elif diff_val == 2:
                dist["double"] += 1
            else:
                dist["worse"] += 1

            if net_diff <= -2:
                net_dist["eagle"] += 1
            elif net_diff == -1:
                net_dist["birdie"] += 1
            elif net_diff == 0:
                net_dist["par"] += 1
            elif net_diff == 1:
                net_dist["bogey"] += 1
            elif net_diff == 2:
                net_dist["double"] += 1
            else:
                net_dist["worse"] += 1

            holes.append({
                "num": hole_num, "par": par,
                "gross": gross, "gross_diff": diff_val,
                "fw": fw, "gir": gir,
                "putts": putts, "penalties": pen,
                "is_par3": is_par3,
                "strokes": strokes, "net": net, "net_diff": net_diff,
                "yds": yds,
            })

        total_par = front_par + back_par
        total_gross = front_gross + back_gross
        total_holes = len(hole_nums)

        if entry_mode == "score_only":
            total_gross = int(round_data.total_gross) if round_data.total_gross else 0
            total_par = 0

        net_total = total_gross - course_handicap if (course_handicap is not None and entry_mode != "score_only") else None
        net_to_par = net_total - total_par if (net_total is not None and total_par) else None

        fir_pct = round(fir_hits / fir_eligible * 100, 1) if fir_eligible else 0
        gir_pct = round(gir_hits / total_holes * 100, 1) if total_holes else 0
        scr_pct = round(scramble_hits / scramble_opps * 100, 1) if scramble_opps else 0

        course_rounds = [r for r in all_rounds_for_user if r.course == round_data.course]
        course_avgs = None
        if course_rounds and len(course_rounds) >= 2:
            courses_dict = {name: dict_to_course(name, d) for name, d in get_courses().items()}
            cf = calc_fir_percent(course_rounds, courses_dict)
            cg = calc_gir_percent(course_rounds)
            cp = calc_putts_per_round(course_rounds)
            cs = calc_scramble_percent(course_rounds, courses_dict)
            csc = calc_scoring_average(course_rounds)
            course_avgs = {
                "fir_pct": round(cf, 1) if cf is not None else None,
                "gir_pct": round(cg, 1) if cg is not None else None,
                "putts": round(cp, 1) if cp is not None else None,
                "scr_pct": round(cs, 1) if cs is not None else None,
                "score": round(csc, 1) if csc is not None else None,
            }

        return render_template("round_detail.html", **base_context(
            round=round_data, course=course, holes=holes,
            entry_mode=entry_mode,
            rating=rating, slope=slope,
            front_nine={
                "gross": front_gross, "par": front_par, "putts": front_putts,
                "net_total": front_net, "net_to_par": front_net - front_par,
                "fir_hits": front_fir_hits, "fir_eligible": front_fir_eligible,
                "gir_hits": front_gir_hits,
                "holes_cnt": front_holes_cnt,
            },
            back_nine={
                "gross": back_gross, "par": back_par, "putts": back_putts,
                "net_total": back_net, "net_to_par": back_net - back_par,
                "fir_hits": back_fir_hits, "fir_eligible": back_fir_eligible,
                "gir_hits": back_gir_hits,
                "holes_cnt": back_holes_cnt,
            },
            total={
                "gross": total_gross, "par": total_par,
                "diff": total_gross - total_par if total_par else None,
                "net_diff": net_to_par, "net_total": net_total,
                "fir_hits": fir_hits, "fir_eligible": fir_eligible,
                "gir_hits": gir_hits, "total_holes": total_holes,
                "putts": total_putts,
                "scramble_hits": scramble_hits, "scramble_opps": scramble_opps,
            },
            dist=dist, net_dist=net_dist,
            round_stats={
                "fir_pct": fir_pct, "gir_pct": gir_pct,
                "putts": total_putts, "scr_pct": scr_pct,
            },
            hi_before=hi_before,
            course_handicap=course_handicap,
            course_avgs=course_avgs,
            edit_mode=edit_mode,
            courses=get_courses(),
        ))

    @app.route("/rounds/<date>/<index>/report")
    @login_required
    def report_card(date, index):
        all_rounds_for_user = get_all_rounds_for_user()
        this_round = None
        for r in all_rounds_for_user:
            if r.date == date and str(r.index) == str(index):
                this_round = r
                break
        if not this_round:
            return "Round not found", 404

        courses_dict = {name: dict_to_course(name, d) for name, d in get_courses().items()}

        l20 = last_n_rounds(all_rounds_for_user, 20)
        if this_round.date not in [r.date for r in all_rounds_for_user[:20]]:
            l20.insert(0, this_round)
            l20 = l20[:20]

        rows = [
            ("Score vs Par", calc_round_vs_par(this_round, courses_dict), calc_avg_vs_par(l20, courses_dict), False, "", 1),
            ("Score vs Rating", calc_round_vs_rating(this_round, courses_dict), calc_avg_vs_rating(l20, courses_dict), False, "", 1),
            ("Par or Better %", calc_par_or_better_percent([this_round], courses_dict), calc_par_or_better_percent(l20, courses_dict), True, "%", 1),
            ("Blow-up Rate", calc_big_number_rate([this_round], courses_dict), calc_big_number_rate(l20, courses_dict), False, "%", 1),
            ("FIR %", calc_fir_percent([this_round], courses_dict), calc_fir_percent(l20, courses_dict), True, "%", 1),
            ("GIR %", calc_gir_percent([this_round]), calc_gir_percent(l20), True, "%", 1),
            ("Putts / Rnd", calc_putts_per_round([this_round]), calc_putts_per_round(l20), False, "", 1),
            ("1-Putt %", calc_one_putt_percent([this_round]), calc_one_putt_percent(l20), True, "%", 1),
            ("2-Putt %", calc_two_putt_percent([this_round]), calc_two_putt_percent(l20), True, "%", 1),
            ("3-Putt %", calc_three_putt_percent([this_round]), calc_three_putt_percent(l20), False, "%", 1),
            ("Scramble %", calc_scramble_percent([this_round], courses_dict), calc_scramble_percent(l20, courses_dict), True, "%", 1),
        ]

        par_this = calc_scoring_avg_by_par_type([this_round], courses_dict)
        par_l20 = calc_scoring_avg_by_par_type(l20, courses_dict)
        for p in [3, 4, 5]:
            rows.append((
                f"Par {p} Avg",
                par_this.get(p),
                par_l20.get(p),
                False, "", 2,
            ))

        rows.append(("Penalties / Rnd", calc_penalties_per_round([this_round]), calc_penalties_per_round(l20), False, "", 1))

        return render_template("report_card.html", **base_context(
            rows=rows, round=this_round,
        ))

    @app.route("/api/rounds/<date>/<index>", methods=["PUT"])
    @login_required
    @csrf.exempt
    def api_rounds_put(date, index):
        all_rounds_for_user = get_all_rounds_for_user()
        old_round = None
        for r in all_rounds_for_user:
            if r.date == date and str(r.index) == str(index):
                old_round = r
                break
        if not old_round:
            return jsonify({"error": "Round not found"}), 404

        data = request.get_json()
        new_date = data.get("date", date)
        if not _valid_date(new_date):
            return jsonify({"error": "Invalid date"}), 400
        course_name = data.get("course", "")
        tees_name = data.get("tees", "")
        course = get_courses().get(course_name, {})
        tees = course.get("tees", {}).get(tees_name, {})

        holes_sel = data.get("holes_played", "18")
        if holes_sel == "front9":
            holes_sel = "front"
        elif holes_sel == "back9":
            holes_sel = "back"
        else:
            holes_sel = "all"

        slope, rating = get_slope_rating(tees, holes_sel)

        _sanitize_scores(data, course, holes_sel)

        # WHS Rule 5.6 / 5.1a: same optional/clamped PCC contract as the
        # POST path (see clamp_pcc), but defaulting to the round's EXISTING
        # pcc (not 0.0) when the field is omitted entirely -- mirrors the
        # `excluded` field's default-to-prior-value pattern immediately
        # below, so an edit made from a form that doesn't surface a PCC
        # input (e.g. the current round_detail.html quick-edit form) can't
        # silently wipe a PCC set at creation time. A request that DOES send
        # "pcc" (including explicit pcc=0) always wins.
        pcc = clamp_pcc(data.get("pcc", old_round.pcc))

        golf_round = {
            "date": new_date,
            "course": course_name,
            "tees": tees_name,
            "holes_played": data.get("holes_played", "18"),
            "holes_selection": holes_sel,
            "transport": data.get("transport", ""),
            "entry_mode": data.get("entry_mode", "detailed"),
            "notes": data.get("notes", ""),
            "holes": data.get("holes", {}),
            "gross_total": data.get("gross_total", ""),
            "excluded": data.get("excluded", old_round.excluded),
            "pcc": pcc,
        }

        total_gross = 0
        if data.get("entry_mode") == "score_only":
            total_gross = _safe_int(data.get("gross_total"), 0)
            golf_round["total_gross"] = str(total_gross)
        elif data.get("holes"):
            for h in data["holes"].values():
                total_gross += _safe_int(h.get("gross"), 0)
            golf_round["total_gross"] = str(total_gross)

        incomplete = (
            data.get("entry_mode") != "score_only"
            and bool(data.get("holes"))
            and _scored_hole_count(data["holes"]) < _expected_hole_count(course, holes_sel)
        )
        skip_differential = incomplete or total_gross <= 0

        # The prior-round scan for this round, shared by the ESC block below
        # (detailed rounds only) and the 9-hole differential combine -- the
        # round being edited is excluded so it can't act as its own "prior".
        rounds_before = [
            r for r in all_rounds_for_user
            if not (r.date == date and str(r.index) == str(index))
        ]
        # Chronological position: same index when the date is unchanged;
        # a date change relocates the round to the slot next_round_index will
        # assign on the new date (lowest free, not necessarily the end).
        before_idx = _safe_int(index, 0) if new_date == date else next_round_index(new_date, current_user.id)

        adjusted_gross = total_gross
        if data.get("entry_mode") != "score_only" and data.get("holes"):
            # WHS Rule 3 / Rule 12 (see POST): ESC course handicap from the
            # prior DISPLAYED HI (0.0 if none), always applied -- matches the
            # recompute/import basis so the differential is entry-path-invariant.
            hi_before = _prior_displayed_hi(rounds_before, new_date, before_idx)
            adj_hi = hi_before / 2 if holes_sel != "all" else hi_before
            course_holes = course.get("holes", {})
            if holes_sel != "all" and course_holes:
                hole_nums = sorted(course_holes.keys(), key=int)
                half = hole_nums[:9] if holes_sel == "front" else hole_nums[9:18]
                played_par = sum(int(course_holes[hn].get("par", 0)) for hn in half)
            else:
                played_par = int(course.get("par", 0))
            course_handicap = calc_course_handicap(adj_hi, played_par, slope, rating)
            ags = calc_adjusted_gross_score(data["holes"], course_holes, course_handicap)
            if ags is not None:
                adjusted_gross = ags

        # --- Differential: lock-aware ---
        diff_override = data.get("differential_override")  # float or None
        send_override = "differential_override" in data
        client_locked = data.get("differential_locked", False)

        if send_override and diff_override is not None:
            # User explicitly provided a new manual value — lock it.
            # WHS Rule 5.1a: round the Score Differential to the nearest tenth
            # with .5 UP (round_half_up), matching every other differential
            # site -- a user-entered 18.25 must store as 18.3, not 18.2.
            differential = round_half_up(float(diff_override), 1)
            golf_round["differential_locked"] = True
            golf_round["differential"] = str(differential)
        elif send_override and diff_override is None:
            # User cleared the lock — recompute. WHS Rule 5.1b: halve pcc for
            # a 9-hole score (effective_pcc), full pcc for "all" (18-hole).
            if skip_differential:
                differential = 0.0
            elif holes_sel != "all":
                # WHS 9-hole combine (see POST) keyed on the prior DISPLAYED
                # HI from this PUT's own prior scan.
                differential = calc_9hole_dif(
                    slope, adjusted_gross, rating,
                    _prior_displayed_hi_or_none(rounds_before, new_date, before_idx),
                    effective_pcc(pcc, holes_sel),
                )
            else:
                differential = calc_round_dif(slope, adjusted_gross, rating, effective_pcc(pcc, holes_sel))
            golf_round["differential_locked"] = False
            golf_round["differential"] = "0" if skip_differential else str(differential)
        elif old_round.differential_locked:
            # Preserve existing lock — don't recompute
            differential = float(old_round.differential)
            golf_round["differential_locked"] = True
            golf_round["differential"] = str(differential)
        else:
            # Normal recompute. WHS Rule 5.1b: same effective_pcc halving as
            # the cleared-lock branch above.
            if skip_differential:
                differential = 0.0
            elif holes_sel != "all":
                # WHS 9-hole combine (see POST) keyed on the prior DISPLAYED
                # HI from this PUT's own prior scan.
                differential = calc_9hole_dif(
                    slope, adjusted_gross, rating,
                    _prior_displayed_hi_or_none(rounds_before, new_date, before_idx),
                    effective_pcc(pcc, holes_sel),
                )
            else:
                differential = calc_round_dif(slope, adjusted_gross, rating, effective_pcc(pcc, holes_sel))
            golf_round["differential_locked"] = False
            golf_round["differential"] = "0" if skip_differential else str(differential)

        if new_date != date:
            # Moving to a different day: claim a free index there so we don't
            # collide with an existing round on that date. The round stays put
            # in the DB until update_round runs, so it isn't counted here.
            new_index = next_round_index(new_date, current_user.id)
        else:
            new_index = int(index)

        golf_round_typed = dict_to_round(golf_round)
        golf_round_typed.index = new_index
        for i, r in enumerate(all_rounds_for_user):
            if r.date == date and str(r.index) == str(index):
                all_rounds_for_user[i] = golf_round_typed
                break
        # In-place replacement -- list stays most-recent-first (WHS ordering
        # contract).
        new_hi = calc_handicap_index(all_rounds_for_user, get_settings().get("include_9hole", True))
        # WHS Rule 5.3: transient displayed value pre-recompute -- clamp to
        # the 54.0 maximum (see the create-path comment above for why
        # `calc_handicap_index` itself is deliberately unclamped).
        if new_hi is not None:
            new_hi = min(new_hi, WHS_MAX_HANDICAP_INDEX)
            golf_round["computed_handicap"] = str(new_hi)
            golf_round_typed.computed_handicap = str(new_hi)

        # Update in place by row id so the round keeps its identity — any
        # match_rounds link (and the round's own URL) survives a date edit.
        updated = update_round(old_round.id, golf_round, new_date, new_index, current_user.id)
        if not updated:
            # Row vanished between the read above and this write (concurrent delete).
            return jsonify({"error": "Round not found"}), 404
        fire_hook("on_round_saved", round_data=golf_round, user_id=current_user.id, db_path=app.config["DB_PATH"])

        # Recompute cascade — update computed_handicap on this user's subsequent rounds
        recompute_handicaps_for_user(current_user.id)

        return jsonify({"ok": True, "differential": differential, "date": new_date, "index": new_index})

    @app.route("/api/rounds/<date>/<index>/exclude", methods=["POST"])
    @login_required
    @csrf.exempt
    def api_rounds_exclude(date, index):
        all_rounds = get_all_rounds_for_user()
        found = any(r.date == date and str(r.index) == str(index) for r in all_rounds)
        if not found:
            return jsonify({"error": "Round not found"}), 404
        data = request.get_json()
        excluded = bool(data.get("excluded", False))
        set_round_excluded(date, int(index), excluded, current_user.id)
        recompute_handicaps_for_user(current_user.id)
        new_all = get_all_rounds_for_user(force=True)
        # WHS Rule 5.7/5.8/5.9: respond with the STORED displayed Handicap
        # Index recompute just wrote (already capped and ESR-adjusted), not
        # a fresh raw calc_handicap_index() recalculation -- the frontend
        # paints this value into the round ledger immediately, so a raw
        # recalc would diverge from every other HI display whenever a cap
        # or Exceptional Score Reduction is active.
        new_hi, _ = current_and_previous_handicap_index(
            new_all, get_settings().get("include_9hole", True)
        )
        return jsonify({"ok": True, "excluded": excluded, "handicap": new_hi})

    @app.route("/api/rounds/<date>/<index>", methods=["DELETE"])
    @login_required
    @csrf.exempt
    def api_rounds_delete(date, index):
        delete_round(date, index, current_user.id)
        recompute_handicaps_for_user(current_user.id)
        return jsonify({"ok": True})

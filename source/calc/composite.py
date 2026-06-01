from dataclasses import dataclass, field
from typing import Any


def last_n_rounds(rounds, n: int) -> list:
    return [r for r in rounds[:n] if not r.excluded]


def best_n_rounds(rounds, n: int) -> list:
    eligible = [r for r in rounds if not r.excluded and r.differential and r.differential != "0"]
    eligible.sort(key=lambda r: float(r.differential))
    return eligible[:min(n, len(eligible))]


@dataclass
class StatPanel:
    key: str
    label: str
    value: Any
    secondary: Any
    higher_better: bool
    color: str
    blank_text: str
    suffix: str = ""


@dataclass
class StatBundle:
    panels: dict[str, StatPanel] = field(default_factory=dict)


def compute_stat_bundle(l20, b8, courses_dict, include_9hole) -> StatBundle:
    from calc import (
        calc_handicap_index,
        calc_scoring_average,
        calc_fir_percent,
        calc_gir_percent,
        calc_putts_per_round,
        calc_scramble_percent,
        calc_one_putt_percent,
        calc_three_putt_percent,
        calc_putts_per_gir,
        calc_par_or_better_percent,
        calc_clean_card_percent,
        calc_big_number_rate,
    )

    def _panel(key, label, color, higher_better, blank_text, value, secondary, suffix=""):
        return StatPanel(key=key, label=label, value=value, secondary=secondary,
                         higher_better=higher_better, color=color,
                         blank_text=blank_text, suffix=suffix)

    definitions = [
        _panel("handicap", "Handicap", "rgb(64,196,255)", False, "Play 3+ rounds to see handicap",
               calc_handicap_index(l20, include_9hole),
               calc_handicap_index(l20[1:], include_9hole)),
        _panel("score", "Avg Score", "rgb(64,255,128)", False, "Play a round to see scoring avg",
               calc_scoring_average(b8), calc_scoring_average(l20)),
        _panel("fir", "FIR", "rgb(255,220,64)", True, "Play a round to see FIR %",
               calc_fir_percent(b8, courses_dict), calc_fir_percent(l20, courses_dict), "%"),
        _panel("gir", "GIR", "rgb(255,128,64)", True, "Play a round to see GIR %",
               calc_gir_percent(b8), calc_gir_percent(l20), "%"),
        _panel("putts", "Putts / Rnd", "rgb(160,128,255)", False, "Play a round to see putts",
               calc_putts_per_round(b8), calc_putts_per_round(l20)),
        _panel("scramble", "Scramble", "rgb(255,64,128)", True, "Play a round to see scramble %",
               calc_scramble_percent(b8, courses_dict), calc_scramble_percent(l20, courses_dict), "%"),
        _panel("one_putt", "1-Putt %", "rgb(128,200,255)", True, "Play a round to see stats",
               calc_one_putt_percent(b8), calc_one_putt_percent(l20), "%"),
        _panel("three_putt", "3-Putt %", "rgb(255,100,100)", False, "Play a round to see stats",
               calc_three_putt_percent(b8), calc_three_putt_percent(l20), "%"),
        _panel("putts_gir", "Putts/GIR", "rgb(200,160,255)", False, "Play a round to see stats",
               calc_putts_per_gir(b8), calc_putts_per_gir(l20)),
        _panel("pob", "Par/Better %", "rgb(100,255,180)", True, "Play a round to see stats",
               calc_par_or_better_percent(b8, courses_dict), calc_par_or_better_percent(l20, courses_dict), "%"),
        _panel("clean_card", "Clean Card %", "rgb(255,220,120)", True, "Play a round to see stats",
               calc_clean_card_percent(b8, courses_dict), calc_clean_card_percent(l20, courses_dict), "%"),
        _panel("big_number", "Blow-up %", "rgb(255,80,80)", False, "Play a round to see stats",
               calc_big_number_rate(b8, courses_dict), calc_big_number_rate(l20, courses_dict), "%"),
    ]

    return StatBundle(panels={p.key: p for p in definitions})

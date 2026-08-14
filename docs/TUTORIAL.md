# Learn to Track Your Golf Game by Recording Your First Round in PinSheet

> By the end of this tutorial, you will have a PinSheet account, one course loaded with tee and hole data, and one recorded round — with real scoring stats waiting for you on the Stats page.

## What You Will Achieve

By the end of this tutorial, you will have:
- Registered the first PinSheet account and reached the Home dashboard
- Added a course ("Fox Hollow") with one tee set and full par/index data for all 18 holes
- Recorded a full 18-hole round using PinSheet's hole-by-hole shorthand
- Viewed your round's score on the Home dashboard and your scoring stats on the Stats page

## Prerequisites

Before starting, you need:
- PinSheet installed and running per the project [README](../README.md) — Python 3.11+, dependencies installed with `pip install -r requirements.txt`, and `SECRET_KEY` set
- A terminal open in the `pinsheet-server` project directory
- A web browser

## Steps

### 1. Start the PinSheet server

In your terminal, run:

```bash
python source/main.py
```

**Expected result:** The terminal prints:

```
PinSheet -> http://127.0.0.1:8080
```

The server is now running and waiting for requests.

### 2. Open PinSheet and register your account

Open `http://127.0.0.1:8080` in your browser.

**Expected result:** You land on the **Sign In** page, because you have no account yet.

Click **Register** at the bottom of the page ("Don't have an account? Register"). Fill in the Create Account form:
- Username: `jsmith`
- Display Name: `J. Smith`
- Password: `golfer2026`
- Confirm Password: `golfer2026`

There is no Invite Code field — you are the first user, so PinSheet makes you admin automatically. Click **Create Account**.

**Expected result:** You are logged in and land on a **Welcome to PinSheet** screen with a single **Get Started** button.

### 3. Enter the app

Click **Get Started**.

**Expected result:** You land on the Home dashboard, titled "Crew standings." A hero panel reads "Your standing," shows **#1 of 1**, and a **Handicap index** tile showing `--` (dashed, since you have no rounds yet).

### 4. Start adding your first course

Click **Courses** in the left sidebar, then click **+ Add Course**.

**Expected result:** You land on the New Course page with a form: Course Name, Location, Tee Sets, and Holes.

Fill in:
- Course Name: `Fox Hollow`
- Location — City: `Denver`, State / Province: `CO`, Country: `USA`

**Expected result:** The fields hold your typed values. One tee set block, labeled "Tee #1," is already on the page — you don't need to click "+ Add Tee" for a single tee set.

### 5. Fill in the tee set and hole grid

In the "Tee #1" block, fill in:
- Tee name: `White`
- Yardage: `6200`
- Rating: `71.2`
- Slope: `128`

Leave Front Rating, Front Slope, Back Rating, and Back Slope blank.

**Expected result:** As soon as you type the tee name, an 18-row hole table appears below, with columns Hole, Par, Index, and "White yds."

Fill in the Par and Index columns for all 18 holes exactly as follows (leave the yardage column blank):

```
Hole  Par  Index
1     4    1
2     4    2
3     3    3
4     5    4
5     4    5
6     4    6
7     3    7
8     5    8
9     4    9
10    4    10
11    4    11
12    3    12
13    5    13
14    4    14
15    4    15
16    3    16
17    5    17
18    4    18
```

**Expected result:** All 18 rows show a Par and an Index value.

### 6. Save the course

Click **Save Course**.

**Expected result:** You land on the Fox Hollow course page. The heading reads "Fox Hollow," and a holes table lists all 18 holes with the pars and indices you entered.

### 7. Start a new round

Click **Rounds** in the left sidebar.

**Expected result:** You land on the Rounds page, showing "0 rounds" and a **+ Log Round** button.

Click **+ Log Round**.

**Expected result:** You land on the New Round page. The Date field is already filled with today's date.

### 8. Walk through the round setup

Click into the Date field, then click anywhere else on the page to confirm it.

**Expected result:** A Course step appears below, with a "Select course..." dropdown.

Select **Fox Hollow**.

**Expected result:** A Tees step appears, with a "Select tees..." dropdown.

Select **White**.

**Expected result:** A Holes Played step appears with three options.

Select **Full 18**.

**Expected result:** A Transport step appears with three options.

Select **Walking**.

**Expected result:** An Entry Mode step appears with two options: "Detailed (hole-by-hole)" and "Score Only."

Select **Detailed (hole-by-hole)**.

**Expected result:** A Hole Scores table appears for all 18 holes, with hole 1 highlighted and an inline text box showing the placeholder "score fw gir putts pen."

### 9. Enter your scorecard hole by hole

PinSheet's shorthand records five values per hole, in order: **score, fairway, green in regulation (GIR), putts, penalties**. Fairway and GIR each need a code — `H` for a hit, a miss-direction code (`L`, `R`, `S`, `LO`, `OBL`, `OBR`, `OBS`, `OBLO`) for a miss, or `N` on a par 3 where fairway doesn't apply. Penalties defaults to `0` if you leave it off.

Type into the highlighted hole's box and press **Enter**. The table advances to the next hole and highlights it automatically. Type these 18 lines, one per hole, in order:

```
5 L S 2
5 R L 2
3 N H 1
6 H S 2
5 L L 2
5 H R 2
4 N H 2
6 R LO 2
3 H H 1
5 L S 2
5 H L 2
4 N H 2
6 H S 3
5 R R 2
7 OBR OBR 2 1
4 N H 2
6 L LO 2
5 H R 2
```

**Expected result:** After hole 18, the wizard advances automatically to a Notes step.

Leave the Notes field blank and click **Continue**.

**Expected result:** A "Add to Match (optional)" step appears with "No match" selected by default.

Click **Save Round**.

**Expected result:** You land on the round detail page. You see a large score of **89**, with a **+17** to-par badge next to it.

### 10. Check your round on the Home dashboard

Click **Home** in the left sidebar.

**Expected result:** The "Your standing" hero still shows **#1 of 1**. The **Handicap index** tile still shows `--`. PinSheet's WHS handicap formula needs a minimum of three recorded rounds before it can calculate an index — that's expected after only one round, not an error.

### 11. Check your scoring stats

Click **Stats** in the left sidebar.

**Expected result:** You land on the Stats > Scoring page. The hero number reads **89.0** next to the label "scoring avg." The stat strip below shows "To Par: 17.0," along with your Par 3, Par 4, and Par 5 averages, Standard Deviation, and Par or Better percentage — all computed from the single round you just recorded.

## What You Learned

You now know how to:
- Register the first PinSheet account with no invite code
- Add a course with a tee set and a full 18-hole par/index grid using the course wizard
- Record a full round using PinSheet's hole-by-hole shorthand (score, fairway, GIR, putts, penalties)
- Read your round score, to-par, and scoring stats immediately after saving — and recognize that the Handicap Index tile stays at `--` until you've logged three rounds

## Related

- **Reference:** [docs/STATS.md](STATS.md) — Full data model and the 50+ derived stats PinSheet computes
- **Reference:** [README.md](../README.md) — Installation, deployment, and multi-user setup

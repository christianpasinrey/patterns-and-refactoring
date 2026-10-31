# Evals

Each scenario is a behaviour the skill must produce, drawn from a failure class seen in real use.
A change to the skill is only proven when a scenario fails on the old version and passes on the
new one.

| Scenario | Failure it pins |
|---|---|
| `requirement-coverage` | One requirement of several silently dropped; tests that never failed |
| `idiom-lookup` | Guard. The per-stack file is skipped, so its depth goes unused |
| `deploy-window` | Guard. A storage change breaks long-lived workers between migrate and restart |
| `standing-rule` | Guard. The YAGNI gate reopens an architecture rule the project already settled |

A guard already passes on the skill as it stands. It stays to catch regressions, and passing it
is why no rule was written for that failure: guidance with no failing baseline is untested text.

## Running one

1. Copy `fixture/` to an empty temporary directory.
2. Start a fresh agent there with the skill installed and give it `prompt.md` verbatim. It must
   not see `checks.md`. To compare versions, tell it instead to read a snapshot's `SKILL.md`.
3. Grade its transcript and result against `checks.md`, reading each one by hand. A check passes
   only on evidence from the run, never on the agent's own claim.

## Reading the results

- **Word the brief like a user.** "Follow the skill and any files it points to" makes agents open
  references they skip in real work, and the scenario then proves nothing about loading.
- **A short clean run is the easy case.** References that fresh agents open on small tasks went
  unread in nearly all of 146 long working sessions. A scenario cannot reproduce that pressure,
  so check real transcripts as well when a change is about loading.
- **Run at least two repetitions.** The same prompt can pass once and fail once.

## Structure

`python scripts/validate.py` checks links, anchors, frontmatter and the manifests.

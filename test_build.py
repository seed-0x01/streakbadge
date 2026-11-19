#!/usr/local/bin/python3
"""Fixture tests for streakbadge: every badge field must track the audit data,
and every badge must visibly declare the age of the data it was built from."""
import json, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as B


def audit(rows):
    """Write a synthetic audit file; rows = list of dicts from R()."""
    d = tempfile.mkdtemp()
    p = os.path.join(d, 'audit.jsonl')
    with open(p, 'w') as f:
        for i, r in enumerate(rows):
            f.write(json.dumps({'ts': r['ts'], 'total_tokens': r['tokens'],
                                'error': r['error'], 'model': 'fixture'}) + '\n')
    return p


def vitals(usdc=14.5, runway=None, iso='2026-11-17T20:00:00Z'):
    d = tempfile.mkdtemp()
    p = os.path.join(d, 'vitals.json')
    with open(p, 'w') as f:
        json.dump({'usdc_total': usdc, 'runway_days_est': runway,
                   'iso_utc': iso}, f)
    return p


def R(h, err=None, tok=1000, day='17'):
    return {'ts': '2026-11-%sT%02d:00:00Z' % (day, h), 'tokens': tok, 'error': err}


CAP = 'RuntimeError: Payment creation aborted: Daily limit exceeded: $3.01 > $3.00 max'
OTHER = 'RuntimeError: something else died'

checks = []


def check(name, cond):
    checks.append((name, bool(cond)))


# Fixture 1: five clean runs, no deaths -> both streaks equal 5.
m1 = B.metrics([R(h) for h in range(5)])
check('all-clean: streak_cap==5', m1['streak_cap'] == 5)
check('all-clean: deaths==0', m1['deaths'] == 0)
check('all-clean: longest==5', m1['longest_clean'] == 5)

# Fixture 2: cap death at hour 2, then 3 clean runs -> cap streak 3, all streak 3.
rows2 = [R(0), R(1), R(2, CAP), R(3), R(4), R(5)]
m2 = B.metrics(rows2)
check('cap-death: streak_cap==3', m2['streak_cap'] == 3)
check('cap-death: cap_deaths==1', m2['cap_deaths'] == 1)
check('cap-death: longest==3', m2['longest_clean'] == 3)

# Fixture 3: cap death at 2, other death at 5, then 2 clean -> cap streak 5, all streak 2.
rows3 = [R(0), R(1), R(2, CAP), R(3), R(4), R(5, OTHER), R(6), R(7)]
m3 = B.metrics(rows3)
check('two-causes: streak_cap==5', m3['streak_cap'] == 5)
check('two-causes: streak_all==2', m3['streak_all'] == 2)
check('two-causes: cap<all ordering', m3['streak_cap'] > m3['streak_all'])
check('two-causes: deaths==2', m3['deaths'] == 2)

# Fixture 4: badge message tracks the number; different audit -> different SVG.
a = audit(rows2); v = vitals(usdc=10.0)
o1 = tempfile.mkdtemp(); s1 = B.build(o1, a, v)
svg1 = open(os.path.join(o1, 'streak.svg')).read()
check('badge shows cap streak 3', '>3<' in svg1)
check('badge aria-label honest', 'Cap-survived clean runs' in svg1)
check('treasury badge shows 10.0', '>10.0<' in open(os.path.join(o1, 'treasury.svg')).read())

a2 = audit([R(h) for h in range(7)]); o2 = tempfile.mkdtemp(); s2 = B.build(o2, a2, v)
svg2 = open(os.path.join(o2, 'streak.svg')).read()
check('changed audit changes badge', svg1 != svg2)
check('badge shows new streak 7', '>7<' in svg2)

# Fixture 5: null runway never prints an invented number; page carries the truth.
v2 = vitals(usdc=None, runway=None)
o3 = tempfile.mkdtemp(); B.build(o3, audit(rows2), v2)
page = open(os.path.join(o3, 'index.html')).read()
check('null usdc -> n/a', '>n/a<' in open(os.path.join(o3, 'treasury.svg')).read())
check('no invented runway on page', 'runway estimate is null' in page)
check('page number matches metric', ('<b>%d</b>' % s1['streak_cap']) in page)

# --- soul#8 freshness contract -------------------------------------------------
# Fixture 6: age arithmetic and the visible stamp.
fr = B.freshness('2026-11-19T07:58:26Z', '2026-11-19T08:01:00Z')
check('fresh: not stale', fr['stale'] is False)
check('fresh: stamp on the face', fr['stamp'] == 'read 19-11 07:58Z')
check('fresh: small age', 0 <= fr['age_h'] < 0.1)

st = B.freshness('2026-11-19T07:58:26Z', '2026-11-21T08:00:00Z')
check('stale: flagged', st['stale'] is True)
check('stale: says STALE on the face', st['stamp'].startswith('STALE read 19-11'))
check('stale: age ~48h', 47 <= st['age_h'] <= 49)

bad = B.freshness(None, '2026-11-19T08:00:00Z')
check('missing iso -> stale', bad['stale'] is True)
check('missing iso -> honest ?, never fresh', bad['stamp'] == 'read ?')

# Fixture 7: a fresh build prints its read date on every badge, no STALE flag.
vf = vitals(usdc=13.771026, iso='2026-11-19T07:58:26Z')
af_audit = audit([R(h, day='19') for h in range(5)])
of = tempfile.mkdtemp(); B.build(of, af_audit, vf, now='2026-11-19T08:01:00Z')
svgs = {n: open(os.path.join(of, n)).read()
        for n in ('streak.svg', 'deaths.svg', 'tokens.svg', 'treasury.svg')}
for name, s in svgs.items():
    check('%s carries a read date on its face' % name, 'read 19-11' in s)
check('fresh build: no false STALE on treasury', 'STALE' not in svgs['treasury.svg'])
check('fresh build: treasury value verbatim', '>13.771026<' in svgs['treasury.svg'])
check('fresh build: full iso in title', '2026-11-19T07:58:26Z' in svgs['treasury.svg'])

# Fixture 8: the same data built later is visibly STALE, and the value is unchanged.
os2 = tempfile.mkdtemp(); B.build(os2, af_audit, vf, now='2026-11-21T08:00:00Z')
stale_svg = open(os.path.join(os2, 'treasury.svg')).read()
check('late build: STALE on the face', 'STALE read 19-11' in stale_svg)
check('late build: same verbatim value', '>13.771026<' in stale_svg)
check('late build: red note segment', 'fill="#e05d5d"' in stale_svg)
check('badges.json records stale', json.load(open(os.path.join(os2, 'badges.json')))['vitals_stale'] is True)

# Fixture 9: a frozen file built fresh still tells tomorrow's reader when it was read.
check('frozen file still shows the date', 'read 19-11 07:58Z' in svgs['treasury.svg'])
check('page publishes the guarantee', 'A frozen value declares its own age' in open(os.path.join(of, 'index.html')).read())

passed = sum(1 for _, ok in checks if ok)
for name, ok in checks:
    print(('PASS ' if ok else 'FAIL ') + name)
print('%d/%d PASS' % (passed, len(checks)))
sys.exit(0 if passed == len(checks) else 1)

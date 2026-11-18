"""DRRAS black-box cases BB-01 through BB-19 against the public HTTP API."""

import itertools
import json
import math
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

root = os.environ['DRRAS_TEST_URL'].rstrip('/') + '/api'
work = Path(os.environ['DRRAS_TEST_RESULTS'])
sc = '/scenarios'
results, trace = [], []
case_id = ''

def http(method, path, payload=None):
    request = Request(root + path, method=method,
                      data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Content-Type':'application/json'})
    try:
        result = urlopen(request, timeout=12)
    except HTTPError as error:
        result = error
    with result:
        status = result.status
        raw_body = result.read().decode(errors='replace')
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        body = raw_body
    trace.append(dict(case=case_id, method=method, path=path, request=payload, status=status, response=body))
    return status, body

def expect(method, path, status=200, payload=None):
    code, body = http(method, path, payload)
    assert code == status, f'{method} {path} returned HTTP {code}. Response {body}. Expected HTTP {status}.'
    return body

def get(path):
    return expect('GET', path)

def post(path, payload=None):
    return expect('POST', path, 201, payload)

def check(passed, evidence):
    assert passed, 'Observed values did not match the expected result. See the HTTP trace.'
    return evidence

def case(id, title, ref, steps, expected, function):
    global case_id
    case_id = id
    try:
        actual, verdict = function(), 'Pass'
    except AssertionError as error:
        actual, verdict = str(error) or 'One or more assertions failed. See HTTP trace.', 'Fail'
    except (URLError, TimeoutError, FileNotFoundError) as error:
        actual, verdict = str(error), 'Blocked'
    except Exception as error:
        actual, verdict = f'{type(error).__name__}: {error}', 'Fail'
    results.append(dict(id=id,title=title,ref=ref,steps=steps,expected=expected,actual=actual,verdict=verdict))
    print(id,verdict,actual,flush=True)

def save():
    (work / 'api_results.json').write_text(json.dumps(results, indent=2))
    (work / 'api_trace.json').write_text(json.dumps(trace, indent=2))

def find(pos, name):
    return next(x for x in pos if x['name']==name)

def validate(scenario, run, matrix):
    capacity = {base['id']: base['quantity'] for base in scenario['bases']}
    demand = {area['id']: area['demand'] for area in scenario['areas']}
    pairs = {(row['baseId'], row['areaId']): row for row in matrix['pairs']}
    sent = dict.fromkeys(capacity, 0)
    received = dict.fromkeys(demand, 0)
    times = []
    cost = 0

    assert run['scenarioId'] == scenario['id'], 'Run points to another scenario.'
    assert run['revision'] == scenario['revision'], 'Run points to another revision.'
    assert run['runtimeMs'] >= 0, 'Negative runtime.'
    for row in run['assignments']:
        base_id = row['baseId']
        area_id = row['areaId']
        quantity = row['quantity']
        minutes = row['travelMinutes']
        assert base_id in capacity and area_id in demand, f'Unknown base or area in {row}.'
        assert type(quantity) is int and quantity > 0, f'Invalid quantity in {row}.'
        pair = pairs[base_id, area_id]
        assert math.isclose(minutes, pair['seconds'] / 60), f'Travel time differs for {row}.'
        assert row['isFallback'] == pair['isFallback'], f'Fallback flag differs for {row}.'
        sent[base_id] += quantity
        received[area_id] += quantity
        times.append(minutes)
        cost += quantity * minutes

    assert all(sent[base_id] <= stock for base_id, stock in capacity.items()), (
        f'Base stock exceeded. Observed {sent}, stock {capacity}.'
    )
    assert all(received[area_id] <= needed for area_id, needed in demand.items()), (
        f'Area demand exceeded. Observed {received}, demand {demand}.'
    )

    assigned = sum(sent.values())
    total_demand = sum(demand.values())
    total_stock = sum(capacity.values())
    metrics = {
        'averageResponseTime': cost / assigned if assigned else 0,
        'maxResponseTime': max(times, default=0),
        'coverageRatio': assigned / total_demand if total_demand else 0,
        'unmetDemand': total_demand - assigned,
        'utilization': assigned / total_stock if total_stock else 0,
        'totalTravelCost': cost,
    }
    for name, expected in metrics.items():
        actual = run['metrics'][name]
        assert math.isclose(expected, actual, abs_tol=1e-8), (
            f'Metric {name}: expected {expected}, got {actual}.'
        )
    return assigned, metrics

if sys.argv[1:] == ['after-restart']:
    previous_run = work / 'persist_before.json'
    results = json.loads((work/'api_results.json').read_text())
    trace = json.loads((work/'api_trace.json').read_text())
    def persist():
        if not previous_run.is_file():
            raise FileNotFoundError('The earlier case did not capture a saved baseline run.')
        old = json.loads(previous_run.read_text())
        s = sc+'/'+old['scenarioId']
        run = get(s+'/runs/'+old['id'])
        history = get(s+'/runs/history')
        return check(run==old and old['id'] in {x['id'] for x in history},
                     f"HTTP 200 after restart. The saved baseline run for revision {run['revision']} matched its pre-restart record and appeared in history.")
    case('BB-19','Saved data after service restart','FR-4.6 / FR-7.1',
         'Restart the test PostgreSQL and API services. Wait for GET /health, then fetch the saved run detail and history for the custom scenario.',
         'After readiness, same saved run, original inputs and metrics are accessible under the same scenario.',persist)
    save()
    sys.exit(results[-1]['verdict'] != 'Pass')

sample_ids = {'musi-flood','coastal-cyclone','urban-earthquake'}
def samples():
    rows = [x for x in get(sc) if x['sample']]
    detail = [get(sc+'/'+x['id']) for x in rows]
    return check({x['id'] for x in detail}==sample_ids and all((len(x['areas']),len(x['bases']))==(4,3) for x in detail),
                 'HTTP 200. Musi River Flooding, Coastal Cyclone and Urban Earthquake each returned four areas and three bases.')
case('BB-01','Load prepared scenarios','FR-1.5 / FR-7.1','GET /scenarios, then GET each of the three built-in scenario IDs.',
     'Three named built-in scenarios appear in the list and are retrievable by ID. Each has four areas and three bases.', samples)

base_location = {'lat':17.385,'lng':78.480}
area = dict(name='Critical site',location=base_location,population=100,severity='Critical',demand=2)
base = dict(name='Near base',location=base_location,quantity=1)
low = dict(name='Low site',location={'lat':17.4,'lng':78.5},population=100,severity='Low',demand=2)
far = dict(name='Far base',location={'lat':17.45,'lng':78.55},quantity=2)
data = {}
def create():
    value=post(sc,dict(name='Black Box Controlled Scenario',region='Hyderabad',description='Synthetic test fixture'))
    data['p']=sc+'/'+value['id']
    current=get(data['p'])
    return check(value==current and value['name']=='Black Box Controlled Scenario' and value['region']=='Hyderabad' and not value['areas'] and not value['bases'],
                 f"HTTP 201 on create and 200 on retrieval. Name and region matched. Revision {current['revision']} contained zero areas and zero bases.")
case('BB-02','Create and retrieve a scenario','FR-1.1 / FR-1.7','POST a scenario named Black Box Controlled Scenario in Hyderabad with description Synthetic test fixture. GET the returned ID.',
     'HTTP 201 then 200 with the same scenario name and region, and empty area and base lists.',create)

def p(suffix=''):
    return data['p']+suffix

def empty():
    error=expect('POST',p('/runs/baseline'),422)
    out=get(p('/runs'))
    return check(out['runs']=={} and 'area' in error['detail'] and 'base' in error['detail'],
                 f"HTTP 422. “{error['detail']}” No current runs returned.")
case('BB-03','Run without required inputs','Use case DR-003 exception',
     'On the empty custom scenario, POST /runs/baseline and GET /runs.',
     'HTTP 422 explains the missing area and base requirement. Current runs stay empty.',empty)

def reject(collection,payload,field):
    before=get(p())
    err=expect('POST',p('/'+collection),422,payload)
    after=get(p())
    fields=', '.join('.'.join(str(i) for i in e['loc'][1:]) for e in err['detail'])
    return check(before==after and field in fields,
                 f'HTTP 422 flagged {fields}. A subsequent GET returned the same revision and scenario data.')
for id, title, ref, collection, payload, field, change in [
    ('BB-04','Unsupported severity','FR-1.3','areas',area|{'severity':'Extreme'},'severity','severity = Extreme'),
    ('BB-05','Demand below minimum','FR-1.6','areas',area|{'demand':-1},'demand','demand = -1'),
    ('BB-06','Negative population','FR-1.6','areas',area|{'population':-1},'population','population = -1'),
    ('BB-07','Latitude out of range','FR-1.6','areas',area|{'location':base_location|{'lat':91}},'location.lat','latitude = 91'),
    ('BB-08','Stock below minimum','FR-1.6','bases',base|{'quantity':-1},'quantity','quantity = -1'),
    ('BB-09','Stock above maximum','API contract','bases',base|{'quantity':1000001},'quantity','quantity = 1,000,001'),
]:
    case(id,title,ref,f"POST to /{collection} on the custom scenario with {change}. Use the {'Critical site' if collection == 'areas' else 'Near base'} fixture for all other values. GET the scenario before and after.",
         f'HTTP 422 identifies {field}. Scenario data and revision stay the same.',
         lambda c=collection,x=payload,f=field: reject(c,x,f))

def add_inputs():
    inputs = {'areas': (area, low), 'bases': (base, far)}
    for collection, fixtures in inputs.items():
        for fixture in fixtures:
            post(p(f'/{collection}'), fixture)

    scenario = get(p())
    data['scenario'] = scenario
    for collection, fixtures in inputs.items():
        saved = scenario[collection]
        assert len(saved) == len(fixtures), f'Unexpected saved {collection}: {saved}.'
        for fixture in fixtures:
            actual = find(saved, fixture['name'])
            for field, expected in fixture.items():
                assert actual[field] == expected, f'{field} differs for {fixture["name"]}.'

    return (
        'Four HTTP 201 responses. HTTP 200 retrieval returned both saved areas and bases '
        f'with the submitted values, at revision {scenario["revision"]}.'
    )
case('BB-10','Save valid areas and bases','FR-1.2 / FR-1.4 / FR-1.7',
     'POST each of the two valid areas and two valid bases from the controlled fixture, then GET the scenario.',
     'Each POST returns HTTP 201. The two areas and two bases are retrieved with all submitted values.',add_inputs)

def baseline():
    initial=get(p('/matrix'))
    run=post(p('/runs/baseline'))
    data['baseline']=run
    matrix=get(p('/matrix'))
    data['matrix']=matrix
    s=data['scenario']
    observed={(x['baseId'],x['areaId']):x['quantity'] for x in run['assignments']}
    near,far=(find(s['bases'],x)['id'] for x in ('Near base','Far base'))
    critical,low=(find(s['areas'],x)['id'] for x in ('Critical site','Low site'))
    n,metrics=validate(s,run,matrix)
    assert initial['pairs']==[] and run['method']=='baseline' and n==3 and observed=={(near,critical):1,(far,critical):1,(far,low):1}, f"Initial pairs {initial['pairs']}. Observed assignments {observed}."
    return f"HTTP 201. Near → Critical 1, Far → Critical 1, Far → Low 1. Coverage {metrics['coverageRatio']:.0%}, unmet demand {metrics['unmetDemand']}, stock utilization {metrics['utilization']:.0%}."
case('BB-11','Severity first baseline','FR-4.1–FR-4.6',
     'GET /matrix before the first run. POST /runs/baseline for the controlled fixture. Read assignments and metrics.',
     'Matrix initially empty. Baseline uses Near for one Critical unit, Far for the second Critical unit, and Far for one Low unit. Coverage 75%, one unmet, utilization 100%.',baseline)

def fallback():
    m=data['matrix']
    s=data['scenario']
    want={(b['id'],a['id']) for b in s['bases'] for a in s['areas']}
    actual={(r['baseId'],r['areaId']) for r in m['pairs']}
    return check(m['revision']==s['revision'] and len(m['pairs'])==4 and want==actual
                 and all(r['isFallback'] and r['seconds']>=0 and r['distanceMeters']>=0 for r in m['pairs'])
                 and data['baseline']['usesFallback'],
                 'HTTP 200. All four unique pairs had nonnegative distance and time. Four fallback flags were true and the baseline run reported usesFallback=true.')
case('BB-12','Create and flag a fallback matrix','FR-3.2 / FR-3.4 / FR-3.5',
     'With OSRM unavailable, GET /matrix after the first custom baseline run. Check the revision, pair keys, distance and time, and the run fallback flag.',
     'Four unique pairs for the two bases and two areas. Each has nonnegative travel values and is identified as fallback. The run also reports fallback.',fallback)

def optimize():
    scenario = data['scenario']
    matrix = data['matrix']
    run = post(p('/runs/optimized'))
    data['optimized'] = run
    assigned, metrics = validate(scenario, run, matrix)
    baseline_run = data['baseline']
    saved = get(p('/runs'))['runs']

    assert run['method'] == 'optimized', 'Wrong method on optimizer response.'
    assert run['id'] != baseline_run['id'], 'The optimizer reused the baseline run ID.'
    assert saved == {'baseline': baseline_run, 'optimized': run}, 'Saved runs differ.'
    assert get(p('/matrix')) == matrix, 'The travel matrix changed.'
    assert get(p())['bases'] == scenario['bases'], 'Base stock changed.'

    times = {(row['baseId'], row['areaId']): row['seconds'] for row in matrix['pairs']}
    pairs = [(base['id'], area['id']) for base in scenario['bases'] for area in scenario['areas']]
    first_stock, second_stock = (base['quantity'] for base in scenario['bases'])
    first_demand, second_demand = (area['demand'] for area in scenario['areas'])
    penalty = 7200
    candidates = []

    # Try each whole-unit plan for the four pairs in this two-base, two-area fixture.
    for quantities in itertools.product(range(3), repeat=4):
        first_to_first, first_to_second, second_to_first, second_to_second = quantities
        outgoing = (first_to_first + first_to_second, second_to_first + second_to_second)
        incoming = (first_to_first + second_to_first, first_to_second + second_to_second)
        if outgoing[0] > first_stock or outgoing[1] > second_stock:
            continue
        if incoming[0] > first_demand or incoming[1] > second_demand:
            continue
        travel_seconds = sum(quantity * times[pair] for quantity, pair in zip(quantities, pairs))
        unmet = first_demand + second_demand - sum(quantities)
        candidates.append(travel_seconds + penalty * unmet)

    actual = round(metrics['totalTravelCost'] * 60) + penalty * metrics['unmetDemand']
    assert assigned == 3, f'Expected 3 assigned units, got {assigned}.'
    assert actual == min(candidates), f'Observed objective {actual} vs minimum {min(candidates)}.'
    return (
        f'HTTP 201. Both runs were retrievable by method at revision {run["revision"]}, '
        f'with the same matrix and source stock. Optimized objective {actual:,} seconds '
        f'equaled the minimum across {len(candidates)} feasible plans.'
    )
case('BB-13','Optimized objective and shared inputs','FR-3.3 / FR-5.2–FR-5.8 / FR-6.1',
     'POST /runs/optimized for the same revision. Re-fetch /runs, /matrix and scenario data. Enumerate feasible quantities 0–2 on each pair with penalty 7,200 seconds per unmet unit.',
     'Two distinct saved runs, identical matrix and source stock, and feasible whole-unit assignments. Optimized objective equals the enumerated minimum for the fixture.',optimize)

def revise():
    old = data['scenario']
    before = get(p('/runs/'+data['baseline']['id']))
    (work/'persist_before.json').write_text(json.dumps(before))
    target=find(old['areas'],'Low site')
    current=expect('DELETE',p('/areas/'+target['id']))
    latest=get(p('/runs'))
    matrix=get(p('/matrix'))
    history=get(p('/runs/history'))
    saved=get(p('/runs/'+before['id']))
    old_matrix=get(p('/matrix?revision='+str(old['revision'])))
    assert current['revision']==old['revision']+1 and len(current['areas'])==1 and all(x['id']!=target['id'] for x in current['areas']), f"Expected Low site removal. Observed areas {current['areas']} and revision {current['revision']}."
    assert not latest['runs'] and not matrix['pairs'] and {data[key]['id'] for key in ('baseline','optimized')} <= {r['id'] for r in history} and saved==before and old_matrix==data['matrix'], f"Revision outputs differ. Current runs {list(latest['runs'])}, current matrix rows {len(matrix['pairs'])}, history rows {len(history)}."
    return f"HTTP 200. Revision advanced {old['revision']} → {current['revision']}. New revision had zero current runs and zero matrix rows. Both older runs remained in history, and the old snapshot retained Low site and all four matrix pairs."
case('BB-14','Revision and historical results','FR-6.1 / FR-7.1 / backend guide',
     'Save a baseline detail response. DELETE Low site. GET current runs and matrix, run history, the earlier baseline detail, and the earlier matrix using its revision query parameter.',
     'Revision advances once. Current run and matrix lists are empty. The earlier runs, baseline snapshot and historical matrix remain readable.',revise)

def zero():
    q=post(sc,dict(name='Black Box Zero Demand',region='Hyderabad'))
    path=sc+'/'+q['id']
    post(path+'/areas',area|{'name':'Zero demand site','demand':0})
    post(path+'/bases',base|{'name':'Maximum stock','quantity':1000000})
    s=get(path)
    assert s['bases'][0]['quantity']==1000000 and s['areas'][0]['demand']==0, f"Boundary values were saved incorrectly, {s}."
    a,b=(post(path+'/runs/'+method) for method in ('baseline','optimized'))
    m=get(path+'/matrix')
    assert all(validate(s,r,m)[0]==0 and not r['assignments'] and all(x==0 for x in r['metrics'].values()) for r in (a,b)), f"Unexpected run results {a['metrics']}, {b['metrics']}."
    return 'Both boundary inputs returned HTTP 201 and were retrieved at 0 demand and 1,000,000 stock. Both runs returned HTTP 201, with no assignments and six zero-valued metrics.'
case('BB-15','Zero demand and maximum stock','FR-1.6 / FR-4.3 / FR-5.3 / API contract',
     'Create a separate scenario. Add one area with demand 0 and one base with stock 1,000,000. Retrieve inputs and run both methods.',
     'Both numbers are accepted. Both methods assign zero ambulances and report zero for the six allocation metrics.',zero)

def sample_runs(slug, name, expected_demand, expected_stock):
    path=sc+'/'+slug
    s=get(path)
    runs=[post(path+'/runs/'+method) for method in ('baseline','optimized')]
    matrix=get(path+'/matrix')
    saved=get(path+'/runs')['runs']
    quantities=[validate(s,r,matrix)[0] for r in runs]
    costs=[r['metrics']['totalTravelCost'] for r in runs]
    unmet=expected_demand-expected_stock
    assert len(matrix['pairs'])==12 and all(row['isFallback'] for row in matrix['pairs']), f'{name} returned {len(matrix["pairs"])} pairs.'
    assert sum(a['demand'] for a in s['areas'])==expected_demand and sum(b['quantity'] for b in s['bases'])==expected_stock and quantities==[expected_stock]*2 and all(saved[r['method']]['id']==r['id'] for r in runs) and costs[1]<=costs[0]+1e-8, f'Observed quantities {quantities} and costs {costs}.'
    return f"Both HTTP 201 and retrievable. Twelve fallback pairs. Each assigned {expected_stock}/{expected_demand} ({expected_stock/expected_demand:.1%}), with {unmet} unmet. Baseline/optimized cost {costs[0]:.2f}/{costs[1]:.2f} unit-min. Run times {runs[0]['runtimeMs']:.2f}/{runs[1]['runtimeMs']:.2f} ms."
for id,slug,name,demand,stock in [('BB-16','musi-flood','Musi River Flooding',26,24),('BB-17','coastal-cyclone','Coastal Cyclone',24,22),('BB-18','urban-earthquake','Urban Earthquake',26,24)]:
    case(id,name,'FR-5.3 / FR-5.6 / FR-7.2',
         'Run both methods on '+name+'. Retrieve current runs and matrix. Recalculate all allocation metrics from the returned assignments, row travel times, demand and base stock.',
         f'Both saved runs use 12 fallback pairs and meet stock/demand constraints. Each uses {stock} of {stock} stock against demand {demand}. Reported metrics match recalculation and optimized cost is at most baseline cost at the same coverage.',
         lambda slug=slug,name=name,demand=demand,stock=stock:sample_runs(slug,name,demand,stock))
save()
sys.exit(any(result['verdict'] != 'Pass' for result in results))

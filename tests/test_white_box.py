"""Source-aware unit cases for the DRRAS allocation, routing, and input branches.

Pratibha Yadav executed W01-W27 on 18 November 2026; the JUnit and coverage
records are saved in docs/evidence. Garv Agrawal's black-box suite is separate.
"""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from backend.app.allocation import (
    AllocationError,
    baseline,
    metrics,
    optimized,
    validate_assignments,
)
from backend.app.models import NewArea, NewBase
from backend.app.routing import Travel, build_matrix, straight_line, table_value


@pytest.fixture
def scenario():
    return {
        "id": "test",
        "areas": [
            {"id": "critical", "severity": "Critical", "demand": 2,
             "location": {"lat": 17.38, "lng": 78.49}},
            {"id": "high", "severity": "High", "demand": 1,
             "location": {"lat": 17.39, "lng": 78.50}},
        ],
        "bases": [
            {"id": "west", "quantity": 2, "location": {"lat": 17.37, "lng": 78.48}},
            {"id": "east", "quantity": 1, "location": {"lat": 17.40, "lng": 78.51}},
        ],
    }


@pytest.fixture
def matrix():
    return {
        ("west", "critical"): Travel(60, 500, False),
        ("east", "critical"): Travel(180, 1500, False),
        ("west", "high"): Travel(120, 1000, False),
        ("east", "high"): Travel(30, 250, False),
    }


def test_W01_baseline_prioritizes_critical(scenario, matrix):
    assert baseline(scenario, matrix) == [
        ("west", "critical", 2), ("east", "high", 1)
    ]


def test_W02_baseline_spills_to_next_base(scenario, matrix):
    scenario["areas"][0]["demand"] = 3
    assert baseline(scenario, matrix) == [
        ("west", "critical", 2), ("east", "critical", 1)
    ]


def test_W03_baseline_does_not_mutate_stock(scenario, matrix):
    before = deepcopy(scenario)
    baseline(scenario, matrix)
    assert scenario == before


def test_W04_baseline_zero_demand(scenario, matrix):
    for area in scenario["areas"]:
        area["demand"] = 0
    assert baseline(scenario, matrix) == []


def test_W05_optimizer_prefers_shorter_route_when_short(scenario, matrix):
    scenario["bases"][0]["quantity"] = 1
    scenario["bases"][1]["quantity"] = 0
    scenario["areas"][0]["demand"] = 1
    matrix["west", "critical"] = Travel(50, 500, False)
    matrix["west", "high"] = Travel(10, 100, False)
    assert optimized(scenario, matrix, 100) == [("west", "high", 1)]


def test_W06_optimizer_covers_demand_when_penalty_is_higher(scenario, matrix):
    result = optimized(scenario, matrix, 7200)
    validate_assignments(scenario, matrix, result)
    assert sum(quantity for _, _, quantity in result) == 3


def test_W07_optimizer_can_leave_demand_unmet_when_route_costs_more(scenario, matrix):
    for travel in list(matrix):
        matrix[travel] = Travel(500, 1000, False)
    assert optimized(scenario, matrix, 100) == []


def test_W08_optimizer_zero_demand(scenario, matrix):
    for area in scenario["areas"]:
        area["demand"] = 0
    assert optimized(scenario, matrix, 7200) == []


def test_W09_validation_accepts_valid_plan(scenario, matrix):
    assert validate_assignments(scenario, matrix, [("west", "critical", 2)]) is None


@pytest.mark.parametrize("plan", [
    [("west", "critical", 1), ("west", "critical", 1)],
    [("west", "critical", 0)],
    [("west", "critical", True)],
    [("missing", "critical", 1)],
], ids=["duplicate", "zero", "boolean", "unknown-pair"])
def test_W10_to_W13_validation_rejects_invalid_pair(scenario, matrix, plan):
    with pytest.raises(AllocationError, match="invalid assignment"):
        validate_assignments(scenario, matrix, plan)


def test_W14_validation_rejects_overstock(scenario, matrix):
    with pytest.raises(AllocationError, match="exceeds the stock"):
        validate_assignments(scenario, matrix, [("west", "critical", 3)])


def test_W15_validation_rejects_overdemand(scenario, matrix):
    with pytest.raises(AllocationError, match="exceeds the demand"):
        validate_assignments(scenario, matrix, [("west", "high", 2)])


def test_W16_metrics_known_plan(scenario, matrix):
    result = metrics(scenario, matrix, [
        ("west", "critical", 2), ("east", "high", 1)
    ])
    assert result == {
        "averageResponseTime": 2.5 / 3,
        "maxResponseTime": 1,
        "coverageRatio": 1,
        "unmetDemand": 0,
        "utilization": 1,
        "totalTravelCost": 2.5,
    }


def test_W17_metrics_empty_plan(scenario, matrix):
    result = metrics(scenario, matrix, [])
    assert result["averageResponseTime"] == 0
    assert result["maxResponseTime"] == 0
    assert result["coverageRatio"] == 0
    assert result["unmetDemand"] == 3
    assert result["utilization"] == 0


def test_W18_straight_line_same_coordinates():
    point = {"lat": 17.38, "lng": 78.49}
    assert straight_line(point, point, 30) == Travel(0, 0, True)


def test_W19_table_value_accepts_zero_and_rejects_bad_values():
    assert table_value([[0, 12]], 0, 0) == 0
    assert table_value([[0, 12]], 0, 1) == 12
    assert table_value([[True]], 0, 0) is None
    assert table_value([[-1]], 0, 0) is None
    assert table_value([[0]], 1, 0) is None


def test_W20_matrix_falls_back_without_osrm(scenario):
    result = build_matrix(scenario, "", 30)
    assert len(result) == 4
    assert all(value.is_fallback for value in result.values())


def test_W21_matrix_uses_valid_osrm_pair_and_falls_back_for_missing(monkeypatch, scenario):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": "Ok",
                "durations": [[12, None], [25, 40]],
                "distances": [[100, None], [250, 400]],
            }

    monkeypatch.setattr("backend.app.routing.httpx.get", lambda *args, **kwargs: Response())
    result = build_matrix(scenario, "https://example.invalid", 30)
    assert result["west", "critical"] == Travel(12, 100, False)
    assert result["west", "high"].is_fallback is True
    assert result["east", "critical"] == Travel(25, 250, False)


def test_W22_model_accepts_coordinate_boundary():
    area = NewArea(name="Edge", location={"lat": 90, "lng": -180},
                   population=0, severity="Low", demand=0)
    assert area.location.lat == 90
    assert area.demand == 0


@pytest.mark.parametrize("change", [
    {"severity": "Extreme"},
    {"demand": -1},
    {"location": {"lat": 91, "lng": 0}},
    {"population": 1.5},
], ids=["severity", "negative-demand", "latitude", "fractional-population"])
def test_W23_to_W26_model_rejects_invalid_area(change):
    data = {"name": "Area", "location": {"lat": 0, "lng": 0},
            "population": 1, "severity": "High", "demand": 1}
    data.update(change)
    with pytest.raises(ValidationError):
        NewArea(**data)


def test_W27_model_rejects_boolean_stock():
    with pytest.raises(ValidationError):
        NewBase(name="Base", location={"lat": 0, "lng": 0}, quantity=True)

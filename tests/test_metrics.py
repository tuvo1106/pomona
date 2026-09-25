import pytest

from pomona.metrics import aggregation_mode


@pytest.mark.parametrize(
    "metric_type",
    [
        "HKQuantityTypeIdentifierStepCount",
        "HKQuantityTypeIdentifierActiveEnergyBurned",
        "HKQuantityTypeIdentifierDistanceWalkingRunning",
        "HKQuantityTypeIdentifierTimeInDaylight",
    ],
)
def test_cumulative_quantities_are_summed(metric_type):
    assert aggregation_mode(metric_type) == "sum"


@pytest.mark.parametrize(
    "metric_type",
    [
        "HKQuantityTypeIdentifierHeartRate",
        "HKQuantityTypeIdentifierBodyMass",
        "HKQuantityTypeIdentifierBloodPressureSystolic",
        "HKQuantityTypeIdentifierOxygenSaturation",
    ],
)
def test_rates_and_point_in_time_readings_are_averaged(metric_type):
    assert aggregation_mode(metric_type) == "avg"


def test_unknown_metric_type_defaults_to_average():
    # Averaging is the safer default for an unrecognized type -- summing an unknown
    # rate-like quantity would silently produce a nonsense number.
    assert aggregation_mode("HKQuantityTypeIdentifierSomeFutureAppleMetric") == "avg"

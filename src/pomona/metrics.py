"""Maps HealthKit record types to how they should be aggregated over a time bucket.

Summing a rate (heart rate, HRV) or a point-in-time reading (weight, SpO2) is meaningless;
those are averaged. Cumulative quantities (steps, energy, distance) are summed.
"""

SUM_TYPES = {
    "HKQuantityTypeIdentifierStepCount",
    "HKQuantityTypeIdentifierActiveEnergyBurned",
    "HKQuantityTypeIdentifierBasalEnergyBurned",
    "HKQuantityTypeIdentifierDistanceWalkingRunning",
    "HKQuantityTypeIdentifierDistanceCycling",
    "HKQuantityTypeIdentifierFlightsClimbed",
    "HKQuantityTypeIdentifierAppleExerciseTime",
    "HKQuantityTypeIdentifierAppleStandTime",
    "HKQuantityTypeIdentifierDietaryWater",
    "HKQuantityTypeIdentifierTimeInDaylight",
}

AVG_TYPES = {
    "HKQuantityTypeIdentifierHeartRate",
    "HKQuantityTypeIdentifierRestingHeartRate",
    "HKQuantityTypeIdentifierWalkingHeartRateAverage",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
    "HKQuantityTypeIdentifierBodyMass",
    "HKQuantityTypeIdentifierBodyMassIndex",
    "HKQuantityTypeIdentifierBodyFatPercentage",
    "HKQuantityTypeIdentifierBloodPressureSystolic",
    "HKQuantityTypeIdentifierBloodPressureDiastolic",
    "HKQuantityTypeIdentifierOxygenSaturation",
    "HKQuantityTypeIdentifierRespiratoryRate",
    "HKQuantityTypeIdentifierVO2Max",
}


def aggregation_mode(metric_type: str) -> str:
    """Returns 'sum' or 'avg' for the given HealthKit record type. Defaults to 'avg'."""
    if metric_type in SUM_TYPES:
        return "sum"
    return "avg"

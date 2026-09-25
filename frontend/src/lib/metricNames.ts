/** Turns a raw HealthKit type identifier into a readable label, e.g.
 * "HKQuantityTypeIdentifierHeartRateVariabilitySDNN" -> "Heart Rate Variability SDNN".
 */
export function friendlyName(type: string): string {
  const stripped = type.replace(/^HK(?:(?:Quantity|Category)TypeIdentifier|DataType)/, '')
  return stripped.replace(/([a-z0-9])([A-Z])/g, '$1 $2')
}

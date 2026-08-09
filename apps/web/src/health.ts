export type HealthState = "checking" | "healthy" | "unavailable";

export function healthLabel(state: HealthState): string {
  switch (state) {
    case "checking":
      return "Checking API";
    case "healthy":
      return "Foundation online";
    case "unavailable":
      return "API unavailable";
  }
}

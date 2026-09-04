import { readFile } from "node:fs/promises";
import path from "node:path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SAMPLE_DATA_DIR = path.resolve(process.cwd(), "..", "sample_data");
const COMMODITY_NAMES: Record<string, string> = {
  bawang_merah: "Bawang Merah",
  beras_medium: "Beras Medium",
  cabai_rawit: "Cabai Rawit",
  bawang_putih: "Bawang Putih",
  beras_premium: "Beras Premium",
  daging_ayam: "Daging Ayam",
  telur_ayam: "Telur Ayam",
};

type Forecast = {
  commodity_code: string;
  city_id: string;
  city_name: string;
  method: string;
  generated_at: string;
  horizon_days: number;
  history_end_date: string;
  forecasts: unknown[];
};

type AnomalyArtifact = {
  schema_version: string;
  generated_at: string;
  method: string;
  active_source_policy: string;
  series_statuses: Array<Record<string, unknown>>;
  events: Array<Record<string, unknown>>;
};

const readJson = async <T>(relativePath: string): Promise<T> =>
  JSON.parse(await readFile(path.join(SAMPLE_DATA_DIR, relativePath), "utf8")) as T;

let forecastsPromise: Promise<Forecast[]> | undefined;
let anomaliesPromise: Promise<AnomalyArtifact> | undefined;
let kabupatenPromise: ReturnType<typeof readKabupaten> | undefined;

function loadForecasts(): Promise<Forecast[]> {
  return forecastsPromise ??= readJson<Forecast[]>(path.join("forecasts", "forecast_all.json"));
}

function loadAnomalies(): Promise<AnomalyArtifact> {
  return anomaliesPromise ??= readJson<AnomalyArtifact>(path.join("anomalies", "anomalies_all.json"));
}

async function readKabupaten() {
  const csv = await readFile(path.join(SAMPLE_DATA_DIR, "kabupaten_jatim.csv"), "utf8");
  return csv.trim().split(/\r?\n/).slice(1).map((line) => {
    const [id, nama, lat, lng, ipm, population, tier] = line.split(",");
    return { id, nama, lat: Number(lat), lng: Number(lng), ipm: Number(ipm), population: Number(population), tier };
  });
}

function loadKabupaten() {
  return kabupatenPromise ??= readKabupaten();
}

function notFound(detail: string) {
  return Response.json({ detail }, { status: 404 });
}

function statusSummary(statuses: Array<Record<string, unknown>>) {
  const states = ["DETECTABLE", "INSUFFICIENT_HISTORY", "NO_ACTIVE_HISTORY"];
  return Object.fromEntries(
    states.map((state) => [state, statuses.filter((status) => status.series_status === state).length]),
  );
}

export async function GET(
  request: Request,
  context: { params: Promise<{ route: string[] }> },
) {
  const { route } = await context.params;
  const endpoint = route.join("/");
  const query = new URL(request.url).searchParams;

  try {
    if (endpoint === "commodities") {
      const codes = [...new Set((await loadForecasts()).map((record) => record.commodity_code))];
      return Response.json(codes.map((code) => ({ code, nama: COMMODITY_NAMES[code] ?? code })));
    }

    if (endpoint === "kabupaten") {
      return Response.json(await loadKabupaten());
    }

    if (endpoint === "forecast") {
      const commodity = query.get("commodity");
      const city = query.get("city");
      if (!commodity || !city) return notFound("commodity and city are required");

      const forecast = (await loadForecasts()).find(
        (record) => record.commodity_code === commodity && record.city_id === city,
      );
      return forecast ? Response.json(forecast) : notFound(`forecast not found for ${commodity}/${city}`);
    }

    if (endpoint === "anomalies") {
      const commodity = query.get("commodity");
      const city = query.get("city");
      const limitValue = Number.parseInt(query.get("limit") ?? "50", 10);
      const limit = Number.isFinite(limitValue) ? Math.min(Math.max(limitValue, 1), 500) : 50;
      const since = query.get("since");
      const artifact = await loadAnomalies();
      const statuses = artifact.series_statuses;

      const matchingStatuses = statuses.filter(
        (status) =>
          (commodity === null || status.commodity_code === commodity) &&
          (city === null || String(status.city_id) === city),
      );

      if (commodity !== null && city !== null) {
        const series = matchingStatuses.find(
          (status) => status.commodity_code === commodity && String(status.city_id) === city,
        );
        if (!series) return notFound(`anomaly series not found for ${commodity}/${city}`);

        const anomalies = artifact.events
          .filter(
            (event) =>
              event.commodity_code === commodity &&
              String(event.city_id) === city &&
              (since === null || String(event.date) >= since),
          )
          .slice(0, limit);
        return Response.json({
          count: anomalies.length,
          method: artifact.method,
          anomalies,
          schema_version: artifact.schema_version,
          artifact_generated_at: artifact.generated_at,
          active_source_policy: artifact.active_source_policy,
          series,
          status_summary: statusSummary([series]),
        });
      }

      const anomalies = artifact.events
        .filter(
          (event) =>
            (commodity === null || event.commodity_code === commodity) &&
            (city === null || String(event.city_id) === city) &&
            (since === null || String(event.date) >= since),
        )
        .slice(0, limit);
      return Response.json({
        count: anomalies.length,
        method: artifact.method,
        anomalies,
        schema_version: artifact.schema_version,
        artifact_generated_at: artifact.generated_at,
        active_source_policy: artifact.active_source_policy,
        series: null,
        status_summary: statusSummary(matchingStatuses),
      });
    }

    return notFound(`local endpoint not available: /api/v1/${endpoint}`);
  } catch (error) {
    console.error("Unable to load local dashboard artifact", error);
    return Response.json({ detail: "local dashboard artifacts are unavailable" }, { status: 503 });
  }
}

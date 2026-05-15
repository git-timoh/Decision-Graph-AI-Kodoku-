/**
 * Shared backend → frontend types.
 *
 * M2 will regenerate this file from the FastAPI OpenAPI schema via
 * `openapi-typescript`. For M1 we hand-write the only shape we need: the
 * healthz response. Keep this file small until the regen script lands.
 */

export type HealthResponse = {
  status: "ok";
  version: string;
};
